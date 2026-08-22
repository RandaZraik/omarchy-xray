from __future__ import annotations

from pathlib import Path
import re
import stat

from xray.config import LIMITS
from xray.files.packages import PackageIndex
from xray.system.commands import CommandRunner
from xray.system.hyprland import window_address
from xray.system.procfs import ProcFs, cgroup_paths, unit_from_cgroup


def _window_integer(value: object, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def normalize_window(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    pid = _window_integer(raw.get("pid"))
    if pid <= 0:
        return None
    position = raw.get("at") if isinstance(raw.get("at"), list) else [0, 0]
    size = raw.get("size") if isinstance(raw.get("size"), list) else [0, 0]
    return {
        "address": str(raw.get("address", "")),
        "pid": pid,
        "class": str(raw.get("class", raw.get("initialClass", ""))),
        "title": str(raw.get("title", raw.get("initialTitle", ""))),
        "workspace": raw.get("workspace", {}),
        "x": _window_integer(position[0]) if len(position) > 0 else 0,
        "y": _window_integer(position[1]) if len(position) > 1 else 0,
        "width": _window_integer(size[0]) if len(size) > 0 else 0,
        "height": _window_integer(size[1]) if len(size) > 1 else 0,
        "focused": bool(raw.get("focusHistoryID") == 0),
        "focusOrder": _window_integer(raw.get("focusHistoryID"), -1),
        "mapped": bool(raw.get("mapped", True)),
        "hidden": bool(raw.get("hidden", False)),
    }


def list_windows(runner: CommandRunner) -> tuple[list[dict[str, object]], str]:
    result = runner.run(["hyprctl", "-j", "clients"])
    if result.returncode != 0:
        return [], "Hyprland window data is unavailable"
    payload, valid = result.json_payload()
    if not valid or not isinstance(payload, list):
        return [], "Hyprland window data is unavailable"
    windows = [window for raw in payload if (window := normalize_window(raw))]
    return windows, ""


def revalidate_window(
    runner: CommandRunner, expected: object
) -> tuple[dict[str, object], str, str]:
    window = expected if isinstance(expected, dict) else {}
    address = window_address(window.get("address"))
    try:
        expected_pid = int(window.get("pid", 0))
    except (TypeError, ValueError):
        expected_pid = 0
    if not address or expected_pid <= 0:
        return {}, address, "Window identity is unavailable"
    windows, error = list_windows(runner)
    if error:
        return {}, address, error
    current = next(
        (
            candidate
            for candidate in windows
            if window_address(candidate.get("address")) == address
            and int(candidate.get("pid", 0)) == expected_pid
        ),
        {},
    )
    if not current:
        return {}, address, "The selected window is no longer available"
    return current, address, ""


def window_for_processes(
    windows: list[dict[str, object]], pids: list[int]
) -> dict[str, object] | None:
    pid_set = set(pids)
    matches = [window for window in windows if int(window["pid"]) in pid_set]
    if not matches:
        return None
    return next((window for window in matches if window["focused"]), matches[0])


def authoritative_window(inferred: object, selected: object) -> dict[str, object]:
    """Keep an explicit picker/query address over any process-tree inference."""
    if isinstance(selected, dict) and selected:
        return dict(selected)
    return dict(inferred) if isinstance(inferred, dict) else {}


def git_context(cwd: str, expected_uid: int | None = None) -> dict[str, str]:
    if not cwd.startswith("/"):
        return {}
    current = Path(cwd)
    for directory in (current, *current.parents):
        git_path = directory / ".git"
        git_type = _owned_path_type(git_path, expected_uid)
        if git_type == "file":
            target = _read_small_text(git_path, expected_uid)
            if target is None:
                continue
            prefix = "gitdir: "
            if not target.startswith(prefix):
                continue
            git_path = Path(directory, target[len(prefix) :]).absolute()
            if _contains_symlink(git_path):
                continue
            git_type = _owned_path_type(git_path, expected_uid)
        if git_type != "directory":
            continue
        head = _read_small_text(git_path / "HEAD", expected_uid) or ""
        branch = (
            head.removeprefix("ref: refs/heads/")
            if head.startswith("ref: refs/heads/")
            else head[:12]
        )
        return {"root": str(directory), "branch": branch}
    return {}


def _contains_symlink(path: Path) -> bool:
    current = Path(path.anchor)
    try:
        for part in path.parts[1:]:
            current /= part
            if current.is_symlink():
                return True
    except OSError:
        return True
    return False


def _owned_path_type(path: Path, expected_uid: int | None) -> str:
    try:
        metadata = path.lstat()
    except OSError:
        return ""
    if expected_uid is not None and metadata.st_uid != expected_uid:
        return ""
    if stat.S_ISREG(metadata.st_mode):
        return "file"
    if stat.S_ISDIR(metadata.st_mode):
        return "directory"
    return ""


def _read_small_text(path: Path, expected_uid: int | None = None) -> str | None:
    if _contains_symlink(path) or _owned_path_type(path, expected_uid) != "file":
        return None
    try:
        with path.open("rb") as handle:
            raw = handle.read(LIMITS.git_metadata_bytes + 1)
    except OSError:
        return None
    if len(raw) > LIMITS.git_metadata_bytes:
        return None
    return raw.decode("utf-8", errors="replace").strip()


def cgroup_context(text: str) -> dict[str, object]:
    paths = cgroup_paths(text)
    joined = "\n".join(paths)
    flatpak_match = re.search(
        r"(?:^|/)(?:app-)?flatpak[-/]([^/]+)", joined, re.IGNORECASE
    )
    container_match = re.search(
        r"(?:docker|libpod|podman|containerd|cri-containerd|nerdctl)[-/:]([a-f0-9]{12,64})"
        r"|kubepods[^\n]*?([a-f0-9]{32,64})",
        joined,
        re.IGNORECASE,
    )
    container_id = (
        next((group for group in container_match.groups() if group), "")
        if container_match
        else ""
    )
    return {
        "paths": paths,
        "unit": unit_from_cgroup(text),
        "flatpak": flatpak_match.group(1).replace("\\x2d", "-")
        if flatpak_match
        else "",
        "container": container_id[:12],
    }


def collect_context(
    proc: ProcFs,
    root: dict[str, object],
    rows: list[dict[str, object]],
    runner: CommandRunner,
    packages: PackageIndex,
    windows: list[dict[str, object]] | None = None,
) -> tuple[dict[str, object], list[str]]:
    limited: list[str] = []
    known_windows = windows
    if known_windows is None:
        known_windows, window_error = list_windows(runner)
        if window_error:
            limited.append(window_error)
    pids = [int(row["pid"]) for row in rows]
    window = window_for_processes(known_windows, pids)
    cgroup = proc.read(int(root["pid"]), "cgroup", limit=131_072)
    cgroup_data = (
        cgroup_context(cgroup.value)
        if cgroup.available
        else {"paths": [], "unit": "", "flatpak": "", "container": ""}
    )
    if cgroup.error == "permission denied":
        limited.append("Control-group context is permission-limited")
    package = packages.owner(str(root.get("executable", "")))
    cwd = str(root.get("cwd", ""))
    return {
        "window": window or {},
        "executable": str(root.get("executable", "")),
        "command": list(root.get("command", [])),
        "workingDirectory": cwd,
        "git": git_context(cwd, int(root.get("uid", -1))),
        "package": {"name": package.name, "version": package.version}
        if package
        else {},
        "launch": cgroup_data,
    }, limited
