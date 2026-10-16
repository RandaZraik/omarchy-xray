import os
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest

from support.live_backend import LiveBackend
from xray.evidence.slowdown import diagnose
from xray.processes.collector import collect_process
from xray.processes.slowdown import SlowdownSampler
from xray.system.procfs import ProcFs


def read_counters(source: Path) -> dict[str, int]:
    return {
        name: int(value)
        for name, value in (line.split() for line in source.read_text().splitlines())
    }


class ProcessMeasurementTruthTests(unittest.TestCase):
    def test_idle_and_busy_cpu_rates_match_independent_process_ticks(self) -> None:
        for busy in (False, True):
            with self.subTest(busy=busy):
                process = subprocess.Popen(
                    [
                        "/usr/bin/python",
                        "-c",
                        "import os,time; os.nice(19); end=time.monotonic()+15\nwhile time.monotonic()<end: pass",
                    ]
                    if busy
                    else ["sleep", "15"]
                )
                try:
                    source = Path(f"/proc/{process.pid}/stat")

                    def ticks() -> int:
                        fields = source.read_text().rpartition(")")[2].split()
                        return int(fields[11]) + int(fields[12])

                    with (
                        TemporaryDirectory() as directory,
                        LiveBackend(Path(directory)) as backend,
                    ):
                        before_first = ticks()
                        first = backend.request("inspect", query=f"pid:{process.pid}")
                        self.assertTrue(first["ok"], first)
                        after_first = ticks()
                        time.sleep(0.4)
                        before_second = ticks()
                        second = backend.request("refresh", compact=True)
                        self.assertTrue(second["ok"], second)
                        after_second = ticks()
                    checks = second["data"]["snapshotPatch"]["performance"]["checks"]
                    work = next(
                        row for row in checks if row["id"] == "performance-cpu-work"
                    )
                    values = work["measurements"]
                    self.assertEqual(values["sampledProcesses"], 1)
                    measured_ticks = (
                        values["cores"]
                        * values["secondsMin"]
                        * os.sysconf("SC_CLK_TCK")
                    )
                    lower = before_second - after_first
                    upper = after_second - before_first
                    self.assertGreaterEqual(measured_ticks + 1e-8, lower)
                    self.assertLessEqual(measured_ticks - 1e-8, upper)
                    if busy:
                        self.assertGreater(measured_ticks, 0)
                    else:
                        self.assertEqual(measured_ticks, 0)
                        self.assertEqual(work["status"], "Quiet")
                    print(
                        "XRAY_CPU_TRUTH "
                        + json.dumps(
                            {
                                "busy": busy,
                                "independentTickBounds": [lower, upper],
                                "measuredTicks": measured_ticks,
                                **values,
                            }
                        )
                    )
                finally:
                    process.terminate()
                    process.wait(timeout=3)

    def test_live_pressure_deltas_match_independent_kernel_reads(self) -> None:
        proc = ProcFs()
        sampler = SlowdownSampler()
        pid = os.getpid()

        def sources() -> dict[str, dict[str, int]]:
            group = next(
                line[3:]
                for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines()
                if line.startswith("0::")
            )
            paths = [
                Path("/proc/pressure") / resource
                for resource in ("cpu", "memory", "io")
            ]
            if group != "/":
                paths += [
                    Path("/sys/fs/cgroup")
                    / group.lstrip("/")
                    / (resource + ".pressure")
                    for resource in ("cpu", "memory", "io")
                ]
            return {
                str(path): {
                    line.split()[0]: int(line.rpartition("total=")[2])
                    for line in path.read_text().splitlines()
                }
                for path in paths
            }

        before_first = sources()
        sampler.sample(proc, [collect_process(proc, pid)[0]])
        after_first = sources()
        time.sleep(0.25)
        before_second = sources()
        raw = sampler.sample(proc, [collect_process(proc, pid)[0]])
        after_second = sources()
        checked = []
        for check in diagnose(raw)["checks"]:
            if not check["id"].startswith("performance-pressure-"):
                continue
            source = check["evidence"][0]
            values = check["measurements"]
            self.assertIn(source, before_first)
            for kind in ("some", "full"):
                delta = values[kind + "Microseconds"]
                if delta is None:
                    continue
                self.assertGreaterEqual(
                    delta, before_second[source][kind] - after_first[source][kind]
                )
                self.assertLessEqual(
                    delta, after_second[source][kind] - before_first[source][kind]
                )
                self.assertAlmostEqual(
                    values[kind + "Percent"],
                    min(100, delta / values["seconds"] / 10000),
                )
            checked.append({"source": source, **values})
        self.assertGreaterEqual(len(checked), 3)
        print("XRAY_PSI_TRUTH " + json.dumps(checked))


@unittest.skipUnless(
    shutil.which("systemd-run") and shutil.which("systemctl"),
    "requires a user systemd manager",
)
class SlowdownTruthTests(unittest.TestCase):
    def test_cpu_throttling_matches_independent_kernel_counter_interval(self) -> None:
        unit = f"xray-slowdown-truth-{os.getpid()}.service"
        launched = subprocess.run(
            [
                "systemd-run",
                "--user",
                "--collect",
                f"--unit={unit}",
                "--property=CPUQuota=10%",
                "--property=Nice=19",
                "--property=MemoryMax=64M",
                "--property=RuntimeMaxSec=15",
                "/usr/bin/python",
                "-c",
                "while True: pass",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if launched.returncode:
            self.skipTest(launched.stderr)
        self.addCleanup(
            subprocess.run,
            ["systemctl", "--user", "stop", unit],
            capture_output=True,
            timeout=5,
            check=False,
        )
        shown = subprocess.run(
            ["systemctl", "--user", "show", unit, "--property=ControlGroup", "--value"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        group = shown.stdout.strip()
        source = Path("/sys/fs/cgroup") / group.lstrip("/") / "cpu.stat"

        with TemporaryDirectory() as directory, LiveBackend(Path(directory)) as backend:
            before_first = read_counters(source)
            first = backend.request("inspect", query=f"service:user:{unit}")
            self.assertTrue(first["ok"], first)
            after_first = read_counters(source)
            time.sleep(0.4)
            before_second = read_counters(source)
            second = backend.request("refresh", compact=True)
            self.assertTrue(second["ok"], second)
            after_second = read_counters(source)
        checks = second["data"]["snapshotPatch"]["performance"]["checks"]
        check = next(
            row for row in checks if row["id"] == "performance-throttle-" + group
        )
        self.assertEqual(check["status"], "Observed", check)
        self.assertAlmostEqual(check["measurements"]["quotaCores"], 0.1)
        for name in ("nr_throttled", "nr_periods", "throttled_usec"):
            self.assertGreaterEqual(
                check["measurements"][name], before_second[name] - after_first[name]
            )
            self.assertLessEqual(
                check["measurements"][name], after_second[name] - before_first[name]
            )
        self.assertGreater(check["measurements"]["throttled_usec"], 0)
        print(
            "XRAY_THROTTLE_TRUTH "
            + json.dumps(
                {
                    "group": group,
                    "beforeFirst": before_first,
                    "afterFirst": after_first,
                    "beforeSecond": before_second,
                    "afterSecond": after_second,
                    "measured": check["measurements"],
                }
            )
        )
        self.assertIn(str(source), " ".join(check["evidence"]))
        configured = Path("/proc/sys/kernel/sched_schedstats").read_text().strip()
        if configured == "0":
            wait = next(row for row in checks if row["id"] == "performance-cpu-wait")
            self.assertEqual(wait["status"], "Unavailable")
            self.assertIsNone(wait["measurements"]["waitMilliseconds"])

    def test_memory_reclaim_events_match_independent_cgroup_counters(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            gate, ready = root / "allocate", root / "ready"
            unit = f"xray-memory-truth-{os.getpid()}.service"
            program = (
                "import pathlib,sys,time\n"
                "gate,ready=map(pathlib.Path,sys.argv[1:])\n"
                "while not gate.exists(): time.sleep(.02)\n"
                "group=next(line[3:] for line in pathlib.Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::'))\n"
                "events=pathlib.Path('/sys/fs/cgroup')/group.lstrip('/')/'memory.events'\n"
                "data=[]\n"
                "while int(dict(line.split() for line in events.read_text().splitlines())['high'])==0 and len(data)<192:\n"
                " data.append(bytearray(256*1024))\n"
                "ready.touch()\ntime.sleep(10)\n"
            )
            launched = subprocess.run(
                [
                    "systemd-run",
                    "--user",
                    "--collect",
                    f"--unit={unit}",
                    "--property=MemoryHigh=24M",
                    "--property=MemoryMax=80M",
                    "--property=MemorySwapMax=0",
                    "--property=Nice=19",
                    "--property=RuntimeMaxSec=15",
                    "/usr/bin/python",
                    "-c",
                    program,
                    str(gate),
                    str(ready),
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if launched.returncode:
                self.skipTest(launched.stderr)
            try:
                group = subprocess.check_output(
                    [
                        "systemctl",
                        "--user",
                        "show",
                        unit,
                        "--property=ControlGroup",
                        "--value",
                    ],
                    text=True,
                    timeout=3,
                ).strip()
                source = Path("/sys/fs/cgroup") / group.lstrip("/") / "memory.events"
                with LiveBackend(root / "state") as backend:
                    before_first = read_counters(source)
                    first = backend.request("inspect", query=f"service:user:{unit}")
                    self.assertTrue(first["ok"], first)
                    after_first = read_counters(source)
                    gate.touch()
                    deadline = time.monotonic() + 6
                    while not ready.exists() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue(
                        ready.exists(), "bounded memory workload did not allocate"
                    )
                    before_second = read_counters(source)
                    second = backend.request("refresh", compact=True)
                    self.assertTrue(second["ok"], second)
                    after_second = read_counters(source)
                checks = second["data"]["snapshotPatch"]["performance"]["checks"]
                check = next(
                    row
                    for row in checks
                    if row["id"] == "performance-memory-events-" + group
                )
                self.assertEqual(check["status"], "Observed", check)
                self.assertGreater(check["measurements"]["high"], 0)
                for name in ("high", "max", "oom", "oom_kill"):
                    self.assertGreaterEqual(
                        check["measurements"][name],
                        before_second[name] - after_first[name],
                    )
                    self.assertLessEqual(
                        check["measurements"][name],
                        after_second[name] - before_first[name],
                    )
                self.assertEqual(after_second["oom_kill"], 0)
                print(
                    "XRAY_MEMORY_TRUTH "
                    + json.dumps(
                        {
                            "beforeFirst": before_first,
                            "afterFirst": after_first,
                            "beforeSecond": before_second,
                            "afterSecond": after_second,
                            "measured": check["measurements"],
                        }
                    )
                )
            finally:
                subprocess.run(
                    ["systemctl", "--user", "stop", unit],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
