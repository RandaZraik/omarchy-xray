from __future__ import annotations

from dataclasses import dataclass
import os

from xray.system.procfs import ProcFs, first_int, parse_key_values


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    start_time: int
    uid: int

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ProcessIdentity:
        return cls(
            int(row.get("pid", 0)),
            int(row.get("startTime", -1)),
            int(row.get("uid", -1)),
        )

    @property
    def key(self) -> str:
        return f"{self.pid}:{self.start_time}"


def parse_stat(text: str) -> dict[str, int | str]:
    left = text.find("(")
    right = text.rfind(")")
    if left < 0 or right <= left:
        raise ValueError("invalid process stat")
    pid = int(text[:left].strip())
    comm = text[left + 1 : right]
    fields = text[right + 2 :].split()
    if len(fields) < 22:
        raise ValueError("incomplete process stat")
    return {
        "pid": pid,
        "comm": comm,
        "state": fields[0],
        "ppid": int(fields[1]),
        "utime": int(fields[11]),
        "stime": int(fields[12]),
        "threads": int(fields[17]),
        "start_time": int(fields[19]),
        "rss_pages": int(fields[21]),
    }


def identity_for(proc: ProcFs, pid: int) -> ProcessIdentity | None:
    stat = proc.read(pid, "stat")
    status = proc.read(pid, "status")
    if not stat.available or not status.available:
        return None
    try:
        parsed = parse_stat(stat.value)
    except (TypeError, ValueError):
        return None
    values = parse_key_values(status.value)
    return ProcessIdentity(
        pid, int(parsed["start_time"]), first_int(values.get("Uid", ""), -1)
    )


def same_user_pids(
    proc: ProcFs, uid: int | None = None, pids: list[int] | None = None
) -> list[int]:
    """Return readable processes owned by the current user without exposing data."""
    expected = os.getuid() if uid is None else uid
    result: list[int] = []
    for pid in proc.pids() if pids is None else pids:
        status = proc.read(pid, "status", limit=131_072)
        if not status.available:
            continue
        values = parse_key_values(status.value)
        if first_int(values.get("Uid", ""), -1) == expected:
            result.append(pid)
    return result
