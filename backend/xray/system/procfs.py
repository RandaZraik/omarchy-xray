from __future__ import annotations

from dataclasses import dataclass
import heapq
import os
from pathlib import Path
import re
import time


@dataclass(frozen=True)
class ReadResult:
    value: str
    error: str = ""

    @property
    def available(self) -> bool:
        return not self.error


class ProcFs:
    """Small, bounded reader for procfs and sysfs-style files."""

    def __init__(
        self, root: Path = Path("/proc"), max_text_bytes: int = 1_048_576
    ) -> None:
        self.root = root
        self.max_text_bytes = max_text_bytes

    def path(self, *parts: str | int) -> Path:
        return self.root.joinpath(*(str(part) for part in parts))

    def pids(self) -> list[int]:
        try:
            return sorted(
                int(entry.name) for entry in self.root.iterdir() if entry.name.isdigit()
            )
        except OSError:
            return []

    def read(self, *parts: str | int, limit: int | None = None) -> ReadResult:
        data, error = self.read_bytes(*parts, limit=limit)
        return ReadResult(
            data.decode("utf-8", errors="replace") if not error else "", error
        )

    def read_bytes(
        self, *parts: str | int, limit: int | None = None
    ) -> tuple[bytes, str]:
        path = self.path(*parts)
        byte_limit = min(limit or self.max_text_bytes, self.max_text_bytes)
        try:
            with path.open("rb") as handle:
                data = handle.read(byte_limit + 1)
            if len(data) > byte_limit:
                return b"", "content exceeds read limit"
            return data, ""
        except PermissionError:
            return b"", "permission denied"
        except FileNotFoundError:
            return b"", "not found"
        except OSError as error:
            return b"", str(error)

    def readlink(self, *parts: str | int) -> ReadResult:
        try:
            # Linux paths are bytes. Python represents undecodable bytes with
            # surrogate code points, which strict JSON output cannot encode.
            raw = os.readlink(self.path(*parts))
            normalized = os.fsencode(raw).decode("utf-8", errors="replace")
            return ReadResult(normalized)
        except PermissionError:
            return ReadResult("", "permission denied")
        except FileNotFoundError:
            return ReadResult("", "not found")
        except OSError as error:
            return ReadResult("", str(error))

    def entries(
        self, *parts: str | int, limit: int | None = None
    ) -> tuple[list[Path], str]:
        try:
            entries = self.path(*parts).iterdir()
            if limit is not None:
                return heapq.nsmallest(limit, entries, key=lambda item: item.name), ""
            return sorted(entries, key=lambda item: item.name), ""
        except PermissionError:
            return [], "permission denied"
        except FileNotFoundError:
            return [], "not found"
        except OSError as error:
            return [], str(error)

    def process_uptime_seconds(self, start_ticks: int) -> tuple[int | None, str]:
        uptime = self.read("uptime", limit=256)
        if not uptime.available:
            return None, f"Process uptime is unavailable: {uptime.error}"
        try:
            boot_elapsed = float(uptime.value.split()[0])
            started = start_ticks / max(1, os.sysconf("SC_CLK_TCK"))
            return max(0, round(boot_elapsed - started)), ""
        except (IndexError, TypeError, ValueError, OSError):
            return None, "Process uptime is unavailable: invalid system counters"

    def process_started_at(self, start_ticks: int) -> tuple[float, str]:
        uptime = self.read("uptime", limit=256)
        if not uptime.available:
            return (
                0.0,
                "Journal history is unavailable because process uptime is unavailable",
            )
        try:
            booted_at = time.time() - float(uptime.value.split()[0])
            started_at = booted_at + start_ticks / max(1, os.sysconf("SC_CLK_TCK"))
            return max(0.0, started_at), ""
        except (IndexError, TypeError, ValueError, OSError):
            return (
                0.0,
                "Journal history is unavailable because the process start time could not be read",
            )


def parse_key_values(text: str, separator: str = ":") -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, found, value = line.partition(separator)
        if found:
            values[key.strip()] = value.strip()
    return values


def cgroup_paths(text: str) -> list[str]:
    return [
        path
        for line in text.splitlines()
        if (path := line.partition("::")[2] or line.rpartition(":")[2])
    ]


def unit_from_cgroup(text: str) -> str:
    for path in cgroup_paths(text):
        for segment in reversed(path.split("/")):
            if segment.endswith((".service", ".scope")):
                return segment
    return ""


def systemd_scope_from_cgroup(text: str) -> str:
    return (
        "user"
        if any(
            re.search(r"/user@\d+\.service(?:/|$)", path) for path in cgroup_paths(text)
        )
        else "system"
    )


def first_int(value: str, fallback: int = 0) -> int:
    try:
        return int(value.split()[0])
    except (IndexError, TypeError, ValueError):
        return fallback
