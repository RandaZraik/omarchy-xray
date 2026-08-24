from __future__ import annotations

from dataclasses import dataclass, field
import time

from xray.system.procfs import ProcFs, first_int, parse_key_values


def total_cpu_ticks(text: str) -> int:
    first_line = text.splitlines()[0] if text else ""
    fields = first_line.split()
    if not fields or fields[0] != "cpu":
        return 0
    total = 0
    # guest and guest_nice are already included in user and nice.
    for value in fields[1:9]:
        try:
            total += int(value)
        except ValueError:
            continue
    return total


def process_io(proc: ProcFs, pid: int) -> tuple[int, int, str]:
    result = proc.read(pid, "io", limit=65_536)
    if not result.available:
        return 0, 0, result.error or "unavailable"
    values = parse_key_values(result.value)
    return (
        first_int(values.get("read_bytes", "0")),
        first_int(values.get("write_bytes", "0")),
        "",
    )


@dataclass
class ActivitySampler:
    previous_total_ticks: int = 0
    previous_at: float = 0.0
    previous_process: dict[str, tuple[int, int | None, int | None]] = field(
        default_factory=dict
    )
    last_limited: list[str] = field(default_factory=list, init=False)

    def sample(
        self,
        proc: ProcFs,
        rows: list[dict[str, object]],
        now: float | None = None,
    ) -> dict[str, object]:
        sampled_at = now if now is not None else time.monotonic()
        cpu = proc.read("stat", limit=65_536)
        current_total = total_cpu_ticks(cpu.value) if cpu.available else 0
        elapsed = max(0.001, sampled_at - self.previous_at) if self.previous_at else 0.0
        total_delta = max(0, current_total - self.previous_total_ticks)
        baseline_ready = self.previous_at > 0 and self.previous_total_ticks > 0
        cpu_available = cpu.available
        current_process: dict[str, tuple[int, int | None, int | None]] = {}
        unavailable_io: list[int] = []
        missing_cpu_baseline: list[int] = []
        missing_io_baseline: list[int] = []
        aggregate_cpu = 0.0
        read_rate = 0.0
        write_rate = 0.0
        for row in rows:
            identity = str(row["id"])
            ticks = int(row.get("cpuTicks", 0))
            pid = int(row["pid"])
            read_bytes, write_bytes, io_error = process_io(proc, pid)
            if io_error:
                unavailable_io.append(pid)
                current_process[identity] = (ticks, None, None)
            else:
                current_process[identity] = (ticks, read_bytes, write_bytes)
            previous = self.previous_process.get(identity)
            if baseline_ready and previous is None:
                missing_cpu_baseline.append(pid)
                if not io_error:
                    missing_io_baseline.append(pid)
            process_cpu = 0.0
            process_read_rate = 0.0
            process_write_rate = 0.0
            if (
                baseline_ready
                and previous
                and cpu_available
                and total_delta > 0
                and elapsed > 0
            ):
                # Match btop's default ``proc_per_core = False`` process-list
                # semantics: a process gets its share of the machine's total
                # CPU capacity. A fully busy thread is therefore roughly
                # 100 / logical_cpu_count percent, not 100 percent.
                process_cpu = max(0.0, (ticks - previous[0]) / total_delta * 100.0)
            if (
                baseline_ready
                and previous
                and not io_error
                and previous[1] is not None
                and previous[2] is not None
                and elapsed > 0
            ):
                process_read_rate = max(0.0, (read_bytes - previous[1]) / elapsed)
                process_write_rate = max(0.0, (write_bytes - previous[2]) / elapsed)
            row["cpuPercent"] = (
                round(process_cpu, 1)
                if cpu_available and baseline_ready and previous is not None
                else None
            )
            row["readBytesPerSecond"] = (
                None
                if io_error or not baseline_ready or previous is None
                else round(process_read_rate)
            )
            row["writeBytesPerSecond"] = (
                None
                if io_error or not baseline_ready or previous is None
                else round(process_write_rate)
            )
            if previous is not None:
                aggregate_cpu += process_cpu
                read_rate += process_read_rate
                write_rate += process_write_rate

        self.previous_total_ticks = current_total
        self.previous_at = sampled_at
        self.previous_process = current_process
        self.last_limited = []
        if not cpu_available:
            self.last_limited.append(
                f"CPU activity counters are unavailable: {cpu.error or 'unknown error'}"
            )
        if unavailable_io:
            joined = ", ".join(str(pid) for pid in unavailable_io[:8])
            suffix = "…" if len(unavailable_io) > 8 else ""
            self.last_limited.append(
                f"Disk I/O counters are unavailable for PID {joined}{suffix}"
            )
        if missing_cpu_baseline:
            self.last_limited.append(
                "CPU activity is collecting a baseline for newly observed processes"
            )
        if missing_io_baseline:
            self.last_limited.append(
                "Disk I/O is collecting a baseline for newly observed processes"
            )
        cpu_ready = cpu_available and baseline_ready and not missing_cpu_baseline
        io_available = not unavailable_io and baseline_ready and not missing_io_baseline
        return {
            "cpuPercent": (round(aggregate_cpu, 1) if cpu_ready else None),
            "cpuAvailable": cpu_ready,
            "cpuStatus": (
                "available"
                if cpu_ready
                else "baseline"
                if cpu_available
                else "unavailable"
            ),
            "memoryBytes": sum(int(row.get("memoryBytes", 0)) for row in rows),
            "threads": sum(int(row.get("threads", 0)) for row in rows),
            "readBytesPerSecond": round(read_rate) if io_available else None,
            "writeBytesPerSecond": round(write_rate) if io_available else None,
            "ioAvailable": io_available,
            "ioStatus": (
                "available"
                if io_available
                else "baseline"
                if not unavailable_io
                else "unavailable"
            ),
            "processCount": len(rows),
        }
