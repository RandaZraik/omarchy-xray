from __future__ import annotations

from pathlib import Path

from support.procfs import stat_line, write_process
from xray.processes.collector import collect_process
from xray.system.procfs import ProcFs


class SlowdownFixture:
    """Small procfs/cgroup fixture with independently controlled kernel counters."""

    def __init__(self, root: Path) -> None:
        self.proc_root = root / "proc"
        self.cgroup_root = root / "cgroup"
        self.proc_root.mkdir()
        self.cgroup_root.mkdir()
        self.proc = ProcFs(self.proc_root)
        self.write_proc(
            "self/mountinfo",
            f"36 27 0:34 / {self.cgroup_root} rw - cgroup2 cgroup2 rw\n",
        )
        self.write_proc("sys/kernel/sched_schedstats", "1\n")
        for resource in ("cpu", "memory", "io"):
            self.write_proc("pressure/" + resource, self.psi())
        self.group("/")
        self.group("/apps")
        self.group("/apps/demo")
        self.process()

    @staticmethod
    def psi(some: int = 0, full: int = 0, average: float = 0) -> str:
        return (
            f"some avg10={average} avg60=0.00 avg300=0.00 total={some}\n"
            f"full avg10=0.00 avg60=0.00 avg300=0.00 total={full}\n"
        )

    def write_proc(self, path: str, value: str) -> None:
        target = self.proc_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)

    def write_group(self, path: str, filename: str, value: str) -> None:
        target = self.cgroup_root / path.lstrip("/") / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)

    def group(self, path: str) -> None:
        for name, value in {
            "cpu.stat": "usage_usec 90000000\nnr_periods 100\nnr_throttled 90\nthrottled_usec 5000000\n",
            "cpu.max": "max 100000\n",
            "memory.events": "low 0\nhigh 100\nmax 100\noom 10\noom_kill 10\n",
            "memory.current": "1048576\n",
            "memory.high": "max\n",
            "memory.max": "max\n",
            **{
                resource + ".pressure": self.psi(1_000_000, 500_000)
                for resource in ("cpu", "memory", "io")
            },
        }.items():
            self.write_group(path, name, value)

    def process(
        self,
        pid: int = 7,
        *,
        start: int = 10,
        group: str = "/apps/demo",
        ticks: int = 10,
    ) -> None:
        write_process(
            self.proc_root,
            pid,
            "worker",
            1,
            start=start,
            ticks=ticks,
            cgroup="0::" + group + "\n",
        )
        self.thread(pid, pid, start=start)

    def thread(
        self,
        pid: int = 7,
        tid: int = 7,
        *,
        start: int = 10,
        run: int = 1_000_000_000,
        wait: int = 500_000_000,
        state: str = "S",
    ) -> None:
        self.write_proc(
            f"{pid}/task/{tid}/stat",
            stat_line(tid, "worker", 1, start).replace(") S ", ") " + state + " "),
        )
        self.write_proc(f"{pid}/task/{tid}/schedstat", f"{run} {wait} 100\n")
        self.write_proc(f"{pid}/task/{tid}/wchan", "io_schedule\n")

    def rows(self, *pids: int) -> list[dict[str, object]]:
        return [collect_process(self.proc, pid)[0] for pid in (pids or (7,))]
