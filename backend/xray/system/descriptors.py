from __future__ import annotations

from dataclasses import dataclass

from xray.config import LIMITS
from xray.system.procfs import ProcFs, ReadResult, first_int


def _permission_limitation(pid: int) -> str:
    return f"Process {pid} descriptors are permission-limited"


@dataclass(frozen=True)
class Descriptor:
    pid: int
    fd: int
    name: str
    target: str
    device: int = -1
    inode: int = -1


@dataclass(frozen=True)
class DescriptorInventory:
    records: tuple[Descriptor, ...]
    limited: tuple[str, ...]
    permission_limited_pids: tuple[int, ...] = ()
    unavailable_pids: tuple[int, ...] = ()

    def catalog_limitations(self) -> tuple[str, ...]:
        per_process = {
            _permission_limitation(pid) for pid in self.permission_limited_pids
        }
        values = [message for message in self.limited if message not in per_process]
        if self.permission_limited_pids:
            values.append(
                "Open file details are unavailable for "
                f"{len(self.permission_limited_pids)} same-user processes"
            )
        return tuple(dict.fromkeys(values))


def collect_descriptors(
    proc: ProcFs,
    pids: list[int],
    *,
    limit_per_process: int = LIMITS.descriptors_per_process,
    total_limit: int = LIMITS.descriptors_total,
) -> DescriptorInventory:
    records: list[Descriptor] = []
    limited: list[str] = []
    permission_limited_pids: set[int] = set()
    unavailable_pids: set[int] = set()
    readlink_limited_pids: set[int] = set()
    exhausted = False
    for pid in pids:
        entries, error = proc.entries(pid, "fd", limit=limit_per_process + 1)
        if error == "permission denied":
            permission_limited_pids.add(pid)
            limited.append(_permission_limitation(pid))
            continue
        if error:
            unavailable_pids.add(pid)
            limited.append(f"Process {pid} descriptors are unavailable: {error}")
            continue
        if len(entries) > limit_per_process:
            limited.append(
                f"Process {pid} descriptors are limited to {limit_per_process}"
            )
        for entry in entries[:limit_per_process]:
            if len(records) >= total_limit:
                exhausted = True
                break
            path = proc.path(pid, "fd", entry.name)
            try:
                before = path.stat()
            except OSError:
                before = None
            target = proc.readlink(pid, "fd", entry.name)
            try:
                after = path.stat()
            except OSError:
                after = None
            confirmed_identity = (
                before is not None
                and after is not None
                and (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
            )
            confirmed_target = (
                target.available
                and (follow_up := proc.readlink(pid, "fd", entry.name)).available
                and follow_up.value == target.value
            )
            if confirmed_target and (
                confirmed_identity or before is None or after is None
            ):
                records.append(
                    Descriptor(
                        pid,
                        first_int(entry.name, -1),
                        entry.name,
                        target.value,
                        after.st_dev if confirmed_identity else -1,
                        after.st_ino if confirmed_identity else -1,
                    )
                )
            else:
                readlink_limited_pids.add(pid)
        if exhausted:
            limited.append(f"Descriptors are limited to {total_limit} total entries")
            break
    limited.extend(
        f"Some descriptor targets are unavailable for process {pid}"
        for pid in sorted(readlink_limited_pids)
    )
    return DescriptorInventory(
        tuple(records),
        tuple(dict.fromkeys(limited)),
        tuple(sorted(permission_limited_pids)),
        tuple(sorted(unavailable_pids | readlink_limited_pids)),
    )


def read_stable_fdinfo(proc: ProcFs, record: Descriptor, *, limit: int) -> ReadResult:
    path = proc.path(record.pid, "fd", record.name)
    try:
        before = path.stat()
    except OSError:
        before = None
    expected = (record.device, record.inode)
    if record.device >= 0 and (
        before is None or expected != (before.st_dev, before.st_ino)
    ):
        return ReadResult("", "descriptor changed during collection")
    target = proc.readlink(record.pid, "fd", record.name)
    if not target.available or target.value != record.target:
        return ReadResult("", "descriptor changed during collection")
    info = proc.read(record.pid, "fdinfo", record.name, limit=limit)
    if not info.available:
        return info
    try:
        after = path.stat()
    except OSError:
        after = None
    follow_up = proc.readlink(record.pid, "fd", record.name)
    if not follow_up.available or follow_up.value != record.target:
        return ReadResult("", "descriptor changed during collection")
    if record.device >= 0 and (
        after is None
        or before is None
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
    ):
        return ReadResult("", "descriptor changed during collection")
    return info
