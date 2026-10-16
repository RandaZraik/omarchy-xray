"""Run the checked-out below calculation code on the same live kernel samples.

Opt in with XRAY_BELOW_SOURCE=/path/to/below. This executes its model code,
not the full below collector or terminal UI. No upstream source is vendored.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from xray.evidence.slowdown import diagnose
from xray.processes.collector import collect_process
from xray.processes.slowdown import SlowdownSampler
from xray.system.procfs import ProcFs


@unittest.skipUnless(
    os.environ.get("XRAY_BELOW_SOURCE") and shutil.which("rustc"),
    "requires a below source checkout and rustc",
)
class BelowReferenceTests(unittest.TestCase):
    def test_actual_below_model_matches_live_counters_in_comparable_units(self) -> None:
        source = Path(os.environ["XRAY_BELOW_SOURCE"])
        model = source / "below/model/src"
        collector = (model / "collector.rs").read_text()
        cgroup = (model / "cgroup.rs").read_text()
        macros = collector[
            collector.index("macro_rules! usec_pct") : collector.index(
                "#[allow(unused)]", collector.index("macro_rules! count_per_sec")
            )
        ]

        def definition(name: str) -> str:
            start = cgroup.index("pub struct " + name)
            return cgroup[
                start : cgroup.index("#[::below_derive::queriable_derives]", start)
            ]

        # These are only the input field types. Calculations and constructors
        # come verbatim from the external checkout, under its own license.
        wrapper = r"""
use std::time::Duration;
mod cgroupfs {
    pub struct CpuStat {
        pub usage_usec: Option<u64>, pub user_usec: Option<u64>, pub system_usec: Option<u64>,
        pub nr_periods: Option<u64>, pub nr_throttled: Option<u64>, pub throttled_usec: Option<u64>,
    }
    #[derive(Clone, Copy)] pub struct PressureLine { pub avg10: Option<f64> }
    pub struct CpuPressure { pub some: PressureLine, pub full: Option<PressureLine> }
    pub struct ResourcePressure { pub some: PressureLine, pub full: PressureLine }
    pub struct Pressure { pub cpu: CpuPressure, pub io: ResourcePressure, pub memory: ResourcePressure }
}
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let n = |i: usize| Some(a[i].parse::<u64>().unwrap());
    let begin = cgroupfs::CpuStat { usage_usec: n(0), user_usec: n(0), system_usec: Some(0), nr_periods: n(1), nr_throttled: n(2), throttled_usec: n(3) };
    let end = cgroupfs::CpuStat { usage_usec: n(4), user_usec: n(4), system_usec: Some(0), nr_periods: n(5), nr_throttled: n(6), throttled_usec: n(7) };
    let cpu = CgroupCpuModel::new(&begin, &end, Duration::from_secs_f64(a[8].parse().unwrap()));
    let line = cgroupfs::PressureLine { avg10: Some(a[9].parse().unwrap()) };
    let pressure = CgroupPressureModel::new(&cgroupfs::Pressure {
        cpu: cgroupfs::CpuPressure { some: line, full: Some(line) },
        io: cgroupfs::ResourcePressure { some: line, full: line },
        memory: cgroupfs::ResourcePressure { some: line, full: line },
    });
    println!("{} {} {} {} {}", cpu.usage_pct.unwrap(), cpu.nr_periods_per_sec.unwrap(), cpu.nr_throttled_per_sec.unwrap(), cpu.throttled_pct.unwrap(), pressure.cpu_some_pct.unwrap());
}
"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            rust = root / "reference.rs"
            rust.write_text(
                macros
                + definition("CgroupCpuModel")
                + definition("CgroupPressureModel")
                + wrapper
            )
            executable = root / "reference"
            subprocess.run(
                [
                    "rustc",
                    "--edition=2021",
                    "-Awarnings",
                    str(rust),
                    "-o",
                    str(executable),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            proc = ProcFs()
            sampler = SlowdownSampler()
            captured = {}
            original_read = ProcFs.read

            def capture(reader, *parts, **kwargs):
                result = original_read(reader, *parts, **kwargs)
                captured[str(reader.path(*parts))] = result.value
                return result

            with patch.object(ProcFs, "read", capture):
                sampler.sample(proc, [collect_process(proc, os.getpid())[0]])
                deadline = time.monotonic() + 0.2
                while time.monotonic() < deadline:
                    pass
                raw = sampler.sample(proc, [collect_process(proc, os.getpid())[0]])
            performance = diagnose(raw)
            comparisons = []
            cpu_sample = raw["cpu"][0]
            cpu_check = next(
                check
                for check in performance["checks"]
                if check["id"] == "performance-cpu-work"
            )
            cpu_usec = cpu_sample["ticks"] * 1_000_000 // os.sysconf("SC_CLK_TCK")
            reference_cpu = float(
                subprocess.check_output(
                    [
                        str(executable),
                        "0",
                        "0",
                        "0",
                        "0",
                        str(cpu_usec),
                        "0",
                        "0",
                        "0",
                        str(cpu_sample["seconds"]),
                        "0",
                    ],
                    text=True,
                    timeout=3,
                ).split()[0]
            )
            self.assertGreater(cpu_usec, 0)
            self.assertAlmostEqual(
                reference_cpu, cpu_check["measurements"]["cores"] * 100, delta=0.001
            )
            comparisons.append(
                {
                    "check": "performance-cpu-work",
                    "belowOneCorePercent": reference_cpu,
                    "xrayOneCorePercent": cpu_check["measurements"]["cores"] * 100,
                }
            )
            for check in performance["checks"]:
                values = check["measurements"]
                if (
                    check["id"].startswith("performance-throttle-")
                    and values.get("status") == "available"
                ):
                    args = [
                        0,
                        0,
                        0,
                        0,
                        0,
                        values["nr_periods"],
                        values["nr_throttled"],
                        values["throttled_usec"],
                        values["seconds"],
                        0,
                    ]
                    actual = [
                        float(value)
                        for value in subprocess.check_output(
                            [str(executable), *map(str, args)], text=True, timeout=3
                        ).split()
                    ]
                    self.assertAlmostEqual(
                        actual[1], values["nr_periods"] / values["seconds"], places=6
                    )
                    self.assertAlmostEqual(
                        actual[2], values["nr_throttled"] / values["seconds"], places=6
                    )
                    self.assertAlmostEqual(
                        actual[3],
                        values["throttled_usec"] / values["seconds"] / 10000,
                        delta=max(0.00001, abs(actual[3]) * 0.00001),
                    )
                    comparisons.append(
                        {"check": check["id"], "below": actual[:4], "xray": values}
                    )
                elif (
                    check["id"].startswith("performance-pressure-")
                    and values.get("someAvg10") is not None
                ):
                    text = captured[check["evidence"][0]]
                    some = next(
                        line for line in text.splitlines() if line.startswith("some ")
                    )
                    average = float(
                        next(
                            field[6:]
                            for field in some.split()
                            if field.startswith("avg10=")
                        )
                    )
                    actual = subprocess.check_output(
                        [
                            str(executable),
                            "0",
                            "0",
                            "0",
                            "0",
                            "0",
                            "0",
                            "0",
                            "0",
                            "1",
                            str(average),
                        ],
                        text=True,
                        timeout=3,
                    )
                    self.assertEqual(float(actual.split()[4]), values["someAvg10"])
                    comparisons.append(
                        {
                            "check": check["id"],
                            "belowAvg10": average,
                            "xrayAvg10": values["someAvg10"],
                            "xrayIntervalEstimate": values["somePercent"],
                        }
                    )
            # Exercise the upstream CPU/throttle arithmetic on nonzero counters
            # too; an idle live scope alone cannot establish those conversions.
            actual = list(
                map(
                    float,
                    subprocess.check_output(
                        [
                            str(executable),
                            "500000",
                            "100",
                            "20",
                            "400000",
                            "1250000",
                            "120",
                            "25",
                            "900000",
                            "2",
                            "4.25",
                        ],
                        text=True,
                        timeout=3,
                    ).split(),
                )
            )
            self.assertEqual(actual, [37.5, 10.0, 2.5, 25.0, 4.25])
            self.assertGreaterEqual(len(comparisons), 3)
            revision = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True, timeout=3
            ).strip()
            print(
                "XRAY_BELOW_COMPARISON "
                + json.dumps(
                    {
                        "revision": revision,
                        "mode": "upstream model code, not full application",
                        "comparisons": comparisons,
                        "nonzeroReferenceCase": actual,
                    }
                )
            )
