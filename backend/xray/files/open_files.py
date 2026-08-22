from __future__ import annotations

import os
from pathlib import Path
import re
from dataclasses import dataclass

from xray.system.procfs import ProcFs, first_int, parse_key_values
from xray.config import LIMITS
from xray.processes.identity import same_user_pids
from xray.system.descriptors import (
    DescriptorInventory,
    collect_descriptors,
    read_stable_fdinfo,
)


_SPECIAL_DESCRIPTOR = re.compile(r"^(socket|pipe|anon_inode):")


@dataclass(frozen=True)
class OpenFileEvidence:
    rows: list[dict[str, object]]
    locks: list[dict[str, object]]
    limited: tuple[str, ...]
    files_complete: bool
    locks_available: bool


def descriptor_kind(target: str) -> str:
    match = _SPECIAL_DESCRIPTOR.match(target)
    if match:
        return match.group(1).replace("anon_inode", "anonymous")
    return "file"


def parse_fdinfo(text: str) -> dict[str, object]:
    values = parse_key_values(text)
    flags_value = values.get("flags", "0")
    try:
        flags = int(flags_value, 8)
    except ValueError:
        flags = 0
    access = flags & os.O_ACCMODE
    mode = (
        "read/write"
        if access == os.O_RDWR
        else "write"
        if access == os.O_WRONLY
        else "read"
    )
    return {
        "position": first_int(values.get("pos", "0")),
        "flags": flags_value,
        "mode": mode,
        "mountId": first_int(values.get("mnt_id", "0")),
    }


def _lock_identity(value: str) -> tuple[int, int, int] | None:
    major, separator, remainder = value.partition(":")
    minor, second_separator, inode = remainder.partition(":")
    if not separator or not second_separator:
        return None
    try:
        return int(major, 16), int(minor, 16), int(inode)
    except ValueError:
        return None


def parse_locks(
    text: str,
    pids: set[int],
    descriptor_files: set[tuple[int, int, int]] | None = None,
) -> list[dict[str, object]]:
    locks: list[dict[str, object]] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 8:
            continue
        try:
            pid = int(fields[4])
        except ValueError:
            continue
        identity = _lock_identity(fields[5])
        owned_ofd = pid == -1 and identity in (descriptor_files or set())
        if pid not in pids and not owned_ofd:
            continue
        locks.append(
            {
                "id": fields[0].rstrip(":"),
                "type": fields[1],
                "scope": fields[2],
                "mode": fields[3].title(),
                "pid": pid,
                "owner": "OFD" if owned_ofd else f"PID {pid}",
                "inode": fields[5],
                "start": fields[6],
                "end": fields[7],
            }
        )
    return locks


def collect_open_files(
    proc: ProcFs,
    pids: list[int],
    *,
    limit_per_process: int = LIMITS.descriptors_per_process,
    inventory: DescriptorInventory | None = None,
) -> OpenFileEvidence:
    rows: list[dict[str, object]] = []
    descriptors = inventory or collect_descriptors(
        proc, pids, limit_per_process=limit_per_process
    )
    limited = list(descriptors.limited)
    files_complete = not descriptors.limited
    fdinfo_failures = 0
    for record in descriptors.records:
        info = read_stable_fdinfo(proc, record, limit=65_536)
        row = {
            "pid": record.pid,
            "fd": record.fd,
            "target": record.target,
            "kind": descriptor_kind(record.target),
            "deleted": record.target.endswith(" (deleted)"),
        }
        if info.available:
            row.update(parse_fdinfo(info.value))
        else:
            fdinfo_failures += 1
            files_complete = False
        rows.append(row)
        if len(rows) >= LIMITS.file_rows:
            limited.append(f"Open files are limited to {LIMITS.file_rows} rows")
            files_complete = False
            break
    if fdinfo_failures:
        limited.append(
            f"Open file metadata is unavailable for {fdinfo_failures} descriptor"
            + ("s" if fdinfo_failures != 1 else "")
        )
    lock_text = proc.read("locks")
    descriptor_files = {
        (os.major(record.device), os.minor(record.device), record.inode)
        for record in descriptors.records
        if record.device >= 0 and descriptor_kind(record.target) == "file"
    }
    locks = (
        parse_locks(lock_text.value, set(pids), descriptor_files)
        if lock_text.available
        else []
    )
    if lock_text.error:
        limited.append(f"Kernel lock table is unavailable: {lock_text.error}")
    rows.sort(
        key=lambda row: (
            str(row["kind"]),
            str(row["target"]),
            int(row["pid"]),
            int(row["fd"]),
        )
    )
    return OpenFileEvidence(
        rows,
        locks,
        tuple(dict.fromkeys(limited)),
        files_complete,
        lock_text.available,
    )


def owners_for_file(
    proc: ProcFs,
    requested: Path,
    inventory: DescriptorInventory | None = None,
) -> list[int]:
    try:
        requested_identity = requested.stat()
    except OSError:
        requested_identity = None
    requested_text = str(requested.resolve(strict=False))
    owners: set[int] = set()
    descriptors = inventory or collect_descriptors(proc, same_user_pids(proc))
    for record in descriptors.records:
        current_target = proc.readlink(record.pid, "fd", record.name)
        if (
            not current_target.available
            or descriptor_kind(current_target.value) != "file"
        ):
            continue
        clean_target = current_target.value.removesuffix(" (deleted)")
        if requested_identity:
            try:
                candidate = proc.path(record.pid, "fd", record.name).stat()
            except OSError:
                continue
            if (candidate.st_dev, candidate.st_ino) == (
                requested_identity.st_dev,
                requested_identity.st_ino,
            ):
                owners.add(record.pid)
        elif clean_target == requested_text:
            owners.add(record.pid)
    return sorted(owners)
