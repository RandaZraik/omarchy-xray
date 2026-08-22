from __future__ import annotations

from pathlib import Path
import re

from xray.config import LIMITS, TIMING
from xray.evidence.redaction import redact_text
from xray.system.commands import CommandRunner
from xray.system.procfs import ProcFs, first_int, parse_key_values


_CAPABILITIES = [
    "CHOWN",
    "DAC_OVERRIDE",
    "DAC_READ_SEARCH",
    "FOWNER",
    "FSETID",
    "KILL",
    "SETGID",
    "SETUID",
    "SETPCAP",
    "LINUX_IMMUTABLE",
    "NET_BIND_SERVICE",
    "NET_BROADCAST",
    "NET_ADMIN",
    "NET_RAW",
    "IPC_LOCK",
    "IPC_OWNER",
    "SYS_MODULE",
    "SYS_RAWIO",
    "SYS_CHROOT",
    "SYS_PTRACE",
    "SYS_PACCT",
    "SYS_ADMIN",
    "SYS_BOOT",
    "SYS_NICE",
    "SYS_RESOURCE",
    "SYS_TIME",
    "SYS_TTY_CONFIG",
    "MKNOD",
    "LEASE",
    "AUDIT_WRITE",
    "AUDIT_CONTROL",
    "SETFCAP",
    "MAC_OVERRIDE",
    "MAC_ADMIN",
    "SYSLOG",
    "WAKE_ALARM",
    "BLOCK_SUSPEND",
    "AUDIT_READ",
    "PERFMON",
    "BPF",
    "CHECKPOINT_RESTORE",
]


def decode_capabilities(value: str) -> list[str]:
    try:
        mask = int(value, 16)
    except ValueError:
        return []
    return [name for index, name in enumerate(_CAPABILITIES) if mask & (1 << index)]


def parse_limits(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines()[1:]:
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 3:
            continue
        rows.append(
            {
                "name": parts[0],
                "soft": parts[1],
                "hard": parts[2],
                "unit": parts[3] if len(parts) > 3 else "",
            }
        )
    return rows


def _mapped_libraries(
    text: str, limit: int = LIMITS.mapped_libraries
) -> tuple[list[str], bool]:
    paths: set[str] = set()
    truncated = False
    for line in text.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) < 6:
            continue
        path = fields[5].removesuffix(" (deleted)")
        file_path = Path(path)
        library_directory = any(
            part in {"lib", "lib32", "lib64", "libx32"} for part in file_path.parts
        )
        shared_object = re.search(r"\.so(?:\.|$)", file_path.name) is not None
        if path.startswith("/") and (shared_object or library_directory):
            paths.add(path)
        if len(paths) > limit:
            truncated = True
            break
    return sorted(paths)[:limit], truncated


def mapped_libraries(text: str, limit: int = LIMITS.mapped_libraries) -> list[str]:
    return _mapped_libraries(text, limit)[0]


def namespace_ids(proc: ProcFs, pid: int) -> tuple[dict[str, str], str]:
    result: dict[str, str] = {}
    entries, error = proc.entries(pid, "ns")
    for entry in entries:
        target = proc.readlink(pid, "ns", entry.name)
        if target.available:
            result[entry.name] = target.value
    return result, error


def collect_security(proc: ProcFs, pid: int) -> tuple[dict[str, object], list[str]]:
    limited: list[str] = []
    status = proc.read(pid, "status")
    values = parse_key_values(status.value) if status.available else {}
    if status.error:
        limited.append(f"Process security status is unavailable: {status.error}")
    apparmor = proc.read(pid, "attr", "current", limit=16_384)
    limits = proc.read(pid, "limits", limit=131_072)
    maps = proc.read(pid, "maps", limit=1_048_576)
    oom_score = proc.read(pid, "oom_score", limit=128)
    oom_adjustment = proc.read(pid, "oom_score_adj", limit=128)
    for result, label in (
        (apparmor, "AppArmor/LSM label"),
        (limits, "Resource limits"),
        (maps, "Mapped libraries"),
        (oom_score, "OOM score"),
        (oom_adjustment, "OOM adjustment"),
    ):
        if result.error:
            limited.append(f"{label} unavailable: {result.error}")
    namespaces, namespace_error = namespace_ids(proc, pid)
    if namespace_error:
        limited.append(f"Process namespaces are unavailable: {namespace_error}")
    libraries, libraries_truncated = (
        _mapped_libraries(maps.value) if maps.available else ([], False)
    )
    if libraries_truncated:
        limited.append(
            f"Mapped libraries are limited to {LIMITS.mapped_libraries} entries"
        )
    return {
        "uid": first_int(values.get("Uid", ""), -1),
        "gid": first_int(values.get("Gid", ""), -1),
        "groups": [
            int(value) for value in values.get("Groups", "").split() if value.isdigit()
        ],
        "statusAvailable": status.available,
        "noNewPrivileges": (
            values.get("NoNewPrivs") == "1" if "NoNewPrivs" in values else None
        ),
        "seccomp": {"0": "Disabled", "1": "Strict", "2": "Filtered"}.get(
            values.get("Seccomp", ""), "Unknown"
        ),
        "capabilities": decode_capabilities(values.get("CapEff", "0")),
        "capabilitiesKnown": "CapEff" in values,
        "apparmor": apparmor.value.strip() if apparmor.available else "",
        "oomScore": (first_int(oom_score.value) if oom_score.available else None),
        "oomAdjustment": (
            first_int(oom_adjustment.value) if oom_adjustment.available else None
        ),
        "namespaces": namespaces,
        "limits": parse_limits(limits.value) if limits.available else [],
        "libraries": libraries,
    }, list(dict.fromkeys(limited))


def collect_logs(
    runner: CommandRunner,
    pid: int,
    started_at: float,
    limit: int = LIMITS.journal_entries,
    scope: str = "user",
    related_pids: list[int] | None = None,
    unit: str = "",
) -> tuple[list[dict[str, str]], str]:
    started_microseconds = max(0, int(started_at * 1_000_000))
    argv = ["journalctl"]
    if scope != "system":
        argv.append("--user")
    selected_pids = list(dict.fromkeys(related_pids or [pid]))
    selected_pids = selected_pids[: LIMITS.journal_processes]
    if unit:
        argv.append(f"--{'user-' if scope != 'system' else ''}unit={unit}")
    else:
        for index, selected_pid in enumerate(selected_pids):
            if index:
                argv.append("+")
            argv.append(f"_PID={selected_pid}")
    argv.extend(
        [
            f"--since=@{max(0, int(started_at))}",
            "--no-pager",
            "--output=json",
            "--lines",
            str(max(1, min(limit, 200))),
        ]
    )
    result = runner.run(
        argv,
        timeout_seconds=TIMING.slower_command_seconds,
    )
    if result.returncode != 0:
        return [], "Journal entries are unavailable"
    rows: list[dict[str, str]] = []
    import json

    for line in result.stdout.splitlines():
        try:
            entry = json.loads(line)
        except (ValueError, RecursionError):
            continue
        try:
            timestamp = int(entry.get("__REALTIME_TIMESTAMP", 0))
        except (TypeError, ValueError):
            timestamp = 0
        if timestamp and timestamp < started_microseconds:
            continue
        rows.append(
            {
                "timestamp": str(entry.get("__REALTIME_TIMESTAMP", "")),
                "priority": str(entry.get("PRIORITY", "")),
                "unit": str(
                    entry.get("_SYSTEMD_USER_UNIT", entry.get("_SYSTEMD_UNIT", ""))
                ),
                "message": redact_text(str(entry.get("MESSAGE", "")))[:4000],
            }
        )
    limited = (
        f"Journal process filters are limited to {LIMITS.journal_processes} entries"
        if not unit
        and related_pids
        and len(set(related_pids)) > LIMITS.journal_processes
        else ""
    )
    return rows, limited
