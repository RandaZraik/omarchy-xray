from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
import time

from xray.config import LIMITS
from xray.processes.identity import ProcessIdentity, identity_for, parse_stat
from xray.system.cgroupfs import collect_scopes, unified_path
from xray.system.procfs import ProcFs, parse_key_values


def unsigned(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 2**64 - 1:
        raise ValueError("counter out of range")
    return parsed


def counters(text: str) -> dict[str, int]:
    values = parse_key_values(text, " ")
    parsed = {key: unsigned(value) for key, value in values.items()}
    if not parsed:
        raise ValueError("invalid counters")
    return parsed


def pressure(text: str) -> dict[str, float | int]:
    result: dict[str, float | int] = {}
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0] not in {"some", "full"}:
            continue
        values = dict(field.split("=", 1) for field in fields[1:])
        average, total = float(values["avg10"]), unsigned(values["total"])
        if not math.isfinite(average) or not 0 <= average <= 100:
            raise ValueError("invalid pressure counters")
        result[fields[0] + "Avg10"] = average
        result[fields[0]] = total
    if "some" not in result:
        raise ValueError("missing pressure counters")
    return result


@dataclass
class SlowdownSampler:
    previous: dict[tuple, tuple[float, dict[str, int]]] = field(default_factory=dict)
    group_memberships: dict[tuple[int, int], frozenset[tuple[ProcessIdentity, str]]] = (
        field(default_factory=dict)
    )

    def sample(
        self, proc: ProcFs, rows: list[dict[str, object]], now: float | None = None
    ) -> dict[str, object]:
        current: dict[tuple, tuple[float, dict[str, int]]] = {}
        scopes, limited, memberships = collect_scopes(proc, rows)
        identities = {int(row["pid"]): ProcessIdentity.from_row(row) for row in rows}
        current_memberships = {
            scope.identity: frozenset(
                (identities[pid], memberships[pid]) for pid in scope.pids
            )
            for scope in scopes
            if scope.path != "/"
        }
        # A worker joining/leaving must not erase a surviving group's interval;
        # require one stable member to avoid bridging a wholly replaced target.
        continuous_groups = {
            identity
            for identity, members in current_memberships.items()
            if members.intersection(self.group_memberships.get(identity, ()))
        }

        def delta(key: tuple, values: dict[str, int]) -> dict[str, object]:
            # Timestamp each source near its read, not the start of a potentially
            # long process-tree scan. Tests can supply a deterministic clock.
            sampled_at = time.monotonic() if now is None else now
            old = self.previous.get(key)
            if key[0] == "cgroup" and key[1] not in continuous_groups:
                old = None
            current[key] = (sampled_at, values)
            if old is None or sampled_at <= old[0] or old[1].keys() != values.keys():
                return {"status": "baseline"}
            differences = {name: value - old[1][name] for name, value in values.items()}
            if any(value < 0 for value in differences.values()):
                return {"status": "baseline"}
            return {
                "status": "available",
                "seconds": sampled_at - old[0],
                **differences,
            }

        def read_pressure(
            reader: ProcFs, parts: tuple, key: tuple
        ) -> dict[str, object]:
            source = str(reader.path(*parts))
            result = reader.read(*parts, limit=4096)
            try:
                if not result.available:
                    raise ValueError(result.error)
                values = pressure(result.value)
            except (ValueError, KeyError):
                return {
                    "status": "unavailable",
                    "source": source,
                    "reason": result.error or "invalid pressure counters",
                }
            change = delta(
                key,
                {
                    name: int(values[name])
                    for name in ("some", "full")
                    if name in values
                },
            )
            return {**values, **change, "source": source}

        groups = []
        for scope in scopes:
            if scope.path == "/":
                continue
            reader = ProcFs(scope.directory)
            key = ("cgroup", scope.identity)
            group: dict[str, object] = {
                "path": scope.path,
                "source": str(scope.directory),
                "pids": list(scope.pids),
                "ancestor": scope.ancestor,
                "pressure": {},
            }
            if not scope.ancestor:
                for resource in ("cpu", "memory", "io"):
                    group["pressure"][resource] = read_pressure(
                        reader, (resource + ".pressure",), (*key, resource)
                    )
            for filename, required in (
                ("cpu.stat", ("nr_periods", "nr_throttled", "throttled_usec")),
                ("memory.events", ("high", "max", "oom", "oom_kill")),
            ):
                result = reader.read(filename, limit=4096)
                try:
                    values = counters(result.value)
                    selected = {name: values[name] for name in required}
                except (ValueError, KeyError):
                    group[filename] = {
                        "status": "unavailable",
                        "reason": result.error or "controller counters unavailable",
                    }
                else:
                    group[filename] = delta((*key, filename), selected)
            quota = reader.read("cpu.max", limit=256)
            try:
                value, period = quota.value.split()
                period_us = unsigned(period)
                quota_us = None if value == "max" else unsigned(value)
                if period_us <= 0 or (quota_us is not None and quota_us <= 0):
                    raise ValueError
                group["cpuQuotaCores"] = (
                    quota_us / period_us if quota_us is not None else None
                )
                group["cpuQuotaKnown"] = True
            except ValueError:
                group["cpuQuotaCores"], group["cpuQuotaKnown"] = None, False
            for filename in ("memory.current", "memory.high", "memory.max"):
                result = reader.read(filename, limit=256)
                try:
                    value = (
                        None
                        if filename != "memory.current"
                        and result.value.strip() == "max"
                        else unsigned(result.value)
                    )
                    group[filename] = {"available": True, "bytes": value}
                except ValueError:
                    group[filename] = {"available": False, "bytes": None}
            try:
                info = scope.directory.stat()
                if (info.st_dev, info.st_ino) != scope.identity:
                    raise ValueError("identity changed")
            except (OSError, ValueError):
                limited.append(f"Cgroup {scope.path} changed during inspection")
                current_memberships.pop(scope.identity, None)
                continue
            groups.append(group)

        host = {
            resource: read_pressure(proc, ("pressure", resource), ("host", resource))
            for resource in ("cpu", "memory", "io")
        }
        enabled = proc.read("sys", "kernel", "sched_schedstats", limit=32)
        scheduler_enabled = enabled.available and enabled.value.strip() == "1"
        threads = []
        process_cpu = []
        thread_limited = False
        remaining = LIMITS.slowdown_threads
        for row in rows:
            pid = int(row["pid"])
            identity = identities[pid]
            cpu_result = proc.read(pid, "stat", limit=4096)
            try:
                stat = parse_stat(cpu_result.value)
                if (stat["pid"], stat["start_time"]) != (pid, identity.start_time):
                    raise ValueError
                cpu = delta(
                    ("cpu", identity),
                    {"ticks": int(stat["utime"]) + int(stat["stime"])},
                )
            except (ValueError, TypeError):
                cpu = {
                    "status": "unavailable",
                    "reason": cpu_result.error
                    or "invalid CPU counters or changed process identity",
                }
            process_cpu.append({"pid": pid, **cpu})
            if remaining <= 0:
                limited.append(
                    f"Thread inspection is limited to {LIMITS.slowdown_threads} entries"
                )
                thread_limited = True
                continue
            tasks, error = proc.entries(pid, "task", limit=remaining + 1)
            if error:
                thread_limited = True
                limited.append(f"PID {pid}: threads are unavailable: {error}")
            if len(tasks) > remaining:
                thread_limited = True
                limited.append(
                    f"Thread inspection is limited to {LIMITS.slowdown_threads} entries"
                )
            for task in tasks[:remaining]:
                remaining -= 1
                if not task.name.isdigit():
                    continue
                tid = int(task.name)
                before = proc.read(pid, "task", tid, "stat", limit=4096)
                try:
                    stat = parse_stat(before.value)
                    if stat["pid"] != tid:
                        raise ValueError
                except (ValueError, TypeError):
                    thread_limited = True
                    limited.append(f"PID {pid} / TID {tid} changed during inspection")
                    continue
                thread: dict[str, object] = {
                    "pid": pid,
                    "tid": tid,
                    "state": stat["state"],
                    "waitChannel": "",
                }
                if stat["state"] == "D":
                    channel = proc.read(pid, "task", tid, "wchan", limit=256)
                    thread["waitChannel"] = (
                        channel.value.strip()
                        if channel.available and channel.value.strip() != "0"
                        else ""
                    )
                if scheduler_enabled:
                    result = proc.read(pid, "task", tid, "schedstat", limit=256)
                    try:
                        run, wait, _slices = (
                            unsigned(value) for value in result.value.split()
                        )
                        thread.update(
                            delta(
                                ("thread", identity, tid, stat["start_time"]),
                                {"runNs": run, "waitNs": wait},
                            )
                        )
                    except ValueError:
                        thread["status"] = "unavailable"
                        limited.append(
                            f"PID {pid} / TID {tid}: scheduler counters are unavailable"
                        )
                else:
                    thread["status"] = "unavailable"
                after = proc.read(pid, "task", tid, "stat", limit=4096)
                try:
                    final = parse_stat(after.value)
                    if (final["pid"], final["start_time"]) != (tid, stat["start_time"]):
                        raise ValueError
                except (ValueError, TypeError):
                    thread_limited = True
                    limited.append(f"PID {pid} / TID {tid} changed during inspection")
                    current.pop(("thread", identity, tid, stat["start_time"]), None)
                    continue
                threads.append(thread)

        changed = set()
        for row in rows:
            pid = int(row["pid"])
            if identity_for(proc, pid) != identities[pid] or (
                pid in memberships
                and unified_path(proc.read(pid, "cgroup", limit=16_384).value)
                != memberships[pid]
            ):
                changed.add(pid)
                limited.append(
                    f"PID {pid}: identity or cgroup changed during performance sampling"
                )
        if changed:
            thread_limited = True
            groups = [
                group for group in groups if not changed.intersection(group["pids"])
            ]
            threads = [thread for thread in threads if thread["pid"] not in changed]
            process_cpu = [cpu for cpu in process_cpu if cpu["pid"] not in changed]
            # Do not let an inconsistent observation seed the next interval.
            current = {key: value for key, value in current.items() if key[0] == "host"}
            current_memberships = {}
        self.previous = current
        self.group_memberships = current_memberships
        return {
            "groups": groups,
            "host": host,
            "threads": threads,
            "cpu": process_cpu,
            "clockTicks": max(1, os.sysconf("SC_CLK_TCK")),
            "schedulerEnabled": scheduler_enabled,
            "threadCoverageLimited": thread_limited,
            "schedulerReason": "Scheduler wait accounting is disabled"
            if enabled.available and enabled.value.strip() == "0"
            else "Scheduler wait accounting is unavailable"
            if not scheduler_enabled
            else "",
            "limited": list(dict.fromkeys(limited)),
        }
