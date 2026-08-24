from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from functools import lru_cache
import os
import pwd
import time

from xray.config import LIMITS, TIMING
from xray.evidence.redaction import redact_command
from xray.processes.identity import ProcessIdentity, identity_for, parse_stat
from xray.system.procfs import ProcFs, first_int, parse_key_values


_PAGE_SIZE = max(1, os.sysconf("SC_PAGE_SIZE"))


@dataclass(frozen=True)
class ProcessCollection:
    root_identity: ProcessIdentity | None
    rows: list[dict[str, object]]
    limited: list[str]
    topology_limited: bool = False


class ProcessMetadataCache:
    def __init__(self) -> None:
        self._rows: dict[tuple[int, int], tuple[float, dict[str, object]]] = {}

    def get(
        self, proc: ProcFs, pid: int, start_time: int, fallback: str
    ) -> dict[str, object]:
        key = (pid, start_time)
        now = time.monotonic()
        cached = self._rows.get(key)
        if not cached or now - cached[0] >= TIMING.process_metadata_refresh_seconds:
            executable = proc.readlink(pid, "exe")
            cwd = proc.readlink(pid, "cwd")
            command, command_limited = _command_line(proc, pid, fallback)
            environment_names, environment_limited = _environment_names(proc, pid)
            metadata_limited = [
                message for message in (command_limited, environment_limited) if message
            ]
            self._rows[key] = (
                now,
                {
                    "command": command,
                    "executable": executable.value if executable.available else "",
                    "cwd": cwd.value if cwd.available else "",
                    "environmentNames": environment_names,
                    "_metadataLimited": metadata_limited,
                },
            )
        return dict(self._rows[key][1])

    def retain(self, identities: set[tuple[int, int]]) -> None:
        self._rows = {
            identity: row
            for identity, row in self._rows.items()
            if identity in identities
        }


@lru_cache(maxsize=128)
def user_name(uid: int) -> str:
    if uid < 0:
        return "unknown"
    try:
        return pwd.getpwuid(uid).pw_name
    except (KeyError, OSError):
        return str(uid)


def _command_line(proc: ProcFs, pid: int, fallback: str) -> tuple[list[str], str]:
    raw, error = proc.read_bytes(pid, "cmdline", limit=LIMITS.process_command_bytes)
    if error or not raw:
        return (
            [fallback] if fallback else [],
            f"Process {pid} command line is unavailable: {error}" if error else "",
        )
    parts = [
        part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part
    ]
    truncated = len(parts) > LIMITS.process_command_arguments
    return (
        redact_command(parts[: LIMITS.process_command_arguments]),
        f"Process {pid} command line is limited to {LIMITS.process_command_arguments} arguments"
        if truncated
        else "",
    )


def _environment_names(proc: ProcFs, pid: int) -> tuple[list[str], str]:
    raw, error = proc.read_bytes(pid, "environ", limit=LIMITS.process_environment_bytes)
    if error:
        return [], f"Process {pid} environment names are unavailable: {error}"
    names = {
        part.partition(b"=")[0].decode("utf-8", errors="replace")
        for part in raw.split(b"\0")
        if b"=" in part and part.partition(b"=")[0]
    }
    ordered = sorted(names)
    truncated = len(ordered) > LIMITS.process_environment_names
    return (
        ordered[: LIMITS.process_environment_names],
        f"Process {pid} environment names are limited to {LIMITS.process_environment_names} entries"
        if truncated
        else "",
    )


def process_name(proc: ProcFs, pid: int) -> str:
    status = proc.read(pid, "status")
    for line in status.value.splitlines() if status.available else []:
        if line.startswith("Name:"):
            return line.partition(":")[2].strip()
    stat = proc.read(pid, "stat")
    if stat.available:
        try:
            return str(parse_stat(stat.value)["comm"])
        except (TypeError, ValueError):
            pass
    return f"PID {pid}"


def collect_process(
    proc: ProcFs,
    pid: int,
    metadata: ProcessMetadataCache | None = None,
) -> tuple[dict[str, object] | None, str]:
    stat_result = proc.read(pid, "stat")
    status_result = proc.read(pid, "status")
    if not stat_result.available:
        return None, stat_result.error
    try:
        stat = parse_stat(stat_result.value)
    except (TypeError, ValueError) as error:
        return None, str(error)

    values = parse_key_values(status_result.value) if status_result.available else {}
    static = (
        metadata.get(proc, pid, int(stat["start_time"]), str(stat["comm"]))
        if metadata
        else ProcessMetadataCache().get(
            proc, pid, int(stat["start_time"]), str(stat["comm"])
        )
    )
    metadata_limited = list(static.get("_metadataLimited", []))
    static.pop("_metadataLimited", None)
    uid = first_int(values.get("Uid", ""), -1)
    row = {
        "id": f"{pid}:{stat['start_time']}",
        "pid": pid,
        "ppid": int(stat["ppid"]),
        "startTime": int(stat["start_time"]),
        "name": values.get("Name", str(stat["comm"])),
        "state": str(stat["state"]),
        "uid": uid,
        "user": user_name(uid),
        "gid": first_int(values.get("Gid", ""), -1),
        "threads": first_int(values.get("Threads", ""), int(stat["threads"])),
        # btop's process list reads resident memory from stat field 24.
        "memoryBytes": max(0, int(stat["rss_pages"])) * _PAGE_SIZE,
        "cpuTicks": int(stat["utime"]) + int(stat["stime"]),
        **static,
    }
    errors = list(metadata_limited)
    if not status_result.available and status_result.error:
        errors.append(f"status is unavailable: {status_result.error}")
    return row, "; ".join(errors)


def process_parent_map(proc: ProcFs, pids: list[int] | None = None) -> dict[int, int]:
    result: dict[int, int] = {}
    for pid in pids if pids is not None else proc.pids():
        stat = proc.read(pid, "stat")
        if not stat.available:
            continue
        try:
            result[pid] = int(parse_stat(stat.value)["ppid"])
        except (TypeError, ValueError):
            continue
    return result


def process_ancestor_map(
    proc: ProcFs, pids: list[int], limit: int = LIMITS.ancestry_depth
) -> dict[int, int]:
    """Collect only the ancestry needed to associate known processes to windows."""
    result: dict[int, int] = {}
    for pid in pids:
        current = pid
        for _ in range(limit):
            if current <= 0 or current in result:
                break
            stat = proc.read(current, "stat")
            if not stat.available:
                break
            try:
                parent = int(parse_stat(stat.value)["ppid"])
            except (TypeError, ValueError):
                break
            result[current] = parent
            current = parent
    return result


def process_tree_parent_map(
    proc: ProcFs, root_pid: int, limit: int = LIMITS.process_tree
) -> dict[int, int] | None:
    """Read one process tree without scanning every process on the machine."""
    parents: dict[int, int] = {root_pid: 0}
    queue = deque([root_pid])
    while queue and len(parents) < limit:
        parent = queue.popleft()
        tasks, task_error = proc.entries(parent, "task", limit=limit + 1)
        if task_error or len(tasks) > limit:
            return None
        for task in tasks:
            if not task.name.isdigit():
                continue
            children = proc.read(parent, "task", task.name, "children", limit=65_536)
            if not children.available:
                return None
            for value in children.value.split():
                try:
                    child = int(value)
                except ValueError:
                    continue
                if child <= 0 or child in parents:
                    continue
                parents[child] = parent
                queue.append(child)
                if len(parents) >= limit:
                    break
            if len(parents) >= limit:
                break
    return parents


def descendant_pids(
    parent_map: dict[int, int], root_pid: int, limit: int = LIMITS.process_tree
) -> list[int]:
    children: dict[int, list[int]] = {}
    for pid, parent in parent_map.items():
        children.setdefault(parent, []).append(pid)
    result: list[int] = []
    queue = deque([root_pid])
    seen: set[int] = set()
    while queue and len(result) < limit:
        pid = queue.popleft()
        if pid in seen:
            continue
        seen.add(pid)
        result.append(pid)
        queue.extend(sorted(children.get(pid, [])))
    return result


def collect_tree(
    proc: ProcFs,
    root_pid: int,
    limit: int = LIMITS.process_tree,
    parent_map: dict[int, int] | None = None,
    metadata: ProcessMetadataCache | None = None,
) -> ProcessCollection:
    root_identity = identity_for(proc, root_pid)
    if not root_identity:
        return ProcessCollection(
            None, [], [f"Process {root_pid} is no longer available"], True
        )

    rows: list[dict[str, object]] = []
    limited: list[str] = []
    parents = parent_map
    if parents is None:
        parents = process_tree_parent_map(proc, root_pid, limit)
    if parents is None:
        parents = process_parent_map(proc)
    pids = descendant_pids(parents, root_pid, limit)
    depths = {root_pid: 0}
    for pid in pids:
        row, error = collect_process(proc, pid, metadata)
        if pid == root_pid and (
            not row or ProcessIdentity.from_row(row) != root_identity
        ):
            return ProcessCollection(
                None,
                [],
                [f"Process {root_pid} changed while it was inspected"],
                True,
            )
        if row:
            parent = parents.get(pid, 0)
            if pid != root_pid and (int(row["ppid"]) != parent or parent not in depths):
                limited.append(f"Process {pid} changed ancestry while it was inspected")
                continue
            depths[pid] = 0 if pid == root_pid else depths.get(parent, 0) + 1
            row["depth"] = depths[pid]
            rows.append(row)
            if error:
                limited.append(
                    f"Process {pid} {error}"
                    if error.startswith("status is unavailable:")
                    else f"Process {pid} metadata is limited: {error}"
                )
        elif error:
            limited.append(f"Process {pid} details are unavailable: {error}")
    if len(pids) >= limit:
        limited.append(f"Process tree is limited to {limit} entries")
    if metadata:
        metadata.retain({(int(row["pid"]), int(row["startTime"])) for row in rows})
    topology_limited = len(pids) >= limit or any(
        "changed ancestry" in message or "details are unavailable" in message
        for message in limited
    )
    return ProcessCollection(
        root_identity, rows, list(dict.fromkeys(limited)), topology_limited
    )
