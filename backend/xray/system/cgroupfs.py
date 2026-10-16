from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re

from xray.config import LIMITS
from xray.system.procfs import ProcFs


def unified_path(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("0::"):
            path = line[3:]
            if (
                path.startswith("/")
                and not any(part in {".", ".."} for part in path.split("/"))
                and "\0" not in path
            ):
                return str(PurePosixPath(path))
    return None


def _unescape(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)


@dataclass(frozen=True)
class CgroupMount:
    root: PurePosixPath
    mountpoint: Path

    def directory(self, group: str) -> Path | None:
        try:
            return self.mountpoint / PurePosixPath(group).relative_to(self.root)
        except ValueError:
            return None


def cgroup_mounts(proc: ProcFs) -> tuple[list[CgroupMount], str]:
    result = proc.read("self", "mountinfo", limit=256 * 1024)
    if not result.available:
        return [], f"Cgroup mounts are unavailable: {result.error}"
    mounts = []
    for line in result.value.splitlines():
        before, separator, after = line.partition(" - ")
        fields = before.split()
        if not separator or after.split()[:1] != ["cgroup2"] or len(fields) < 6:
            continue
        root, mountpoint = _unescape(fields[3]), _unescape(fields[4])
        if unified_path("0::" + root) is None or not mountpoint.startswith("/"):
            continue
        mounts.append(CgroupMount(PurePosixPath(root), Path(mountpoint)))
    mounts.sort(key=lambda mount: len(mount.root.parts), reverse=True)
    return mounts, "" if mounts else "Cgroup v2 is not mounted in X-Ray's namespace"


@dataclass(frozen=True)
class CgroupScope:
    path: str
    directory: Path
    identity: tuple[int, int]
    pids: tuple[int, ...]
    ancestor: bool


def collect_scopes(
    proc: ProcFs, rows: list[dict[str, object]]
) -> tuple[list[CgroupScope], list[str], dict[int, str]]:
    mounts, error = cgroup_mounts(proc)
    if error:
        return [], [error], {}
    members: dict[str, list[int]] = {}
    limited: list[str] = []
    paths: dict[int, str] = {}
    for row in rows:
        pid = int(row["pid"])
        result = proc.read(pid, "cgroup", limit=16_384)
        path = unified_path(result.value) if result.available else None
        if path is None:
            limited.append(f"PID {pid}: cgroup v2 membership is unavailable")
            continue
        paths[pid] = path
        members.setdefault(path, []).append(pid)

    # Visit direct memberships first, then their parents, so a deep hierarchy
    # cannot consume the whole budget before another process's own group.
    pending = deque((PurePosixPath(path), pids, 0) for path, pids in members.items())
    scopes: dict[Path, CgroupScope] = {}
    seen: set[tuple[str, tuple[int, ...]]] = set()
    while pending:
        group, pids, depth = pending.popleft()
        marker = (str(group), tuple(pids))
        if marker in seen:
            continue
        seen.add(marker)
        mount = next((m for m in mounts if m.directory(str(group)) is not None), None)
        if mount is None:
            limited.append(f"Cgroup {group} is outside the visible cgroup mounts")
            continue
        directory = mount.directory(str(group))
        assert directory is not None
        existing = scopes.get(directory)
        if existing:
            scopes[directory] = CgroupScope(
                existing.path,
                directory,
                existing.identity,
                tuple(sorted(set(existing.pids) | set(pids))),
                existing.ancestor and depth > 0,
            )
        elif len(scopes) >= LIMITS.slowdown_cgroups:
            limited.append(
                f"Performance collection is limited to {LIMITS.slowdown_cgroups} cgroups"
            )
            continue
        else:
            try:
                # A replaced directory must not inherit the old counters.
                info = directory.stat()
                if directory.resolve() != directory.absolute():
                    raise ValueError("symbolic cgroup path")
            except (OSError, ValueError) as error:
                limited.append(f"Cgroup {group} is unavailable: {error}")
                continue
            scopes[directory] = CgroupScope(
                str(group),
                directory,
                (info.st_dev, info.st_ino),
                tuple(pids),
                depth > 0,
            )
        if group != PurePosixPath("/"):
            if not any(m.directory(str(group.parent)) is not None for m in mounts):
                limited.append(
                    f"Ancestors above {group} are not visible in the cgroup mounts"
                )
            elif depth + 1 < LIMITS.slowdown_cgroup_depth:
                pending.append((group.parent, pids, depth + 1))
            else:
                limited.append("Cgroup ancestor inspection reached its depth limit")
    return list(scopes.values()), list(dict.fromkeys(limited)), paths
