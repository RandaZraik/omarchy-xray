from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from xray.processes.activity import ActivitySampler, total_cpu_ticks
from xray.system.procfs import ProcFs


class ActivityTests(unittest.TestCase):
    def test_total_cpu_ticks(self) -> None:
        self.assertEqual(total_cpu_ticks("cpu  1 2 3 4 5\ncpu0 1 1\n"), 15)
        self.assertEqual(total_cpu_ticks("cpu 1 2 3 4 5 6 7 8 100 200\n"), 36)

    def test_rates_require_a_previous_sample_and_use_process_identity(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "7").mkdir()
            (root / "7/io").write_text(
                "read_bytes: 100\nwrite_bytes: 200\n", encoding="utf-8"
            )
            (root / "stat").write_text("cpu 100 0 0 900\n", encoding="utf-8")
            rows = [
                {
                    "id": "7:10",
                    "pid": 7,
                    "cpuTicks": 10,
                    "memoryBytes": 50,
                    "threads": 2,
                }
            ]
            sampler = ActivitySampler()
            first = sampler.sample(ProcFs(root), rows, now=1.0)
            (root / "7/io").write_text(
                "read_bytes: 300\nwrite_bytes: 500\n", encoding="utf-8"
            )
            (root / "stat").write_text("cpu 110 0 0 990\n", encoding="utf-8")
            rows[0]["cpuTicks"] = 20
            second = sampler.sample(ProcFs(root), rows, now=3.0)

        self.assertIsNone(first["cpuPercent"])
        self.assertEqual(first["cpuStatus"], "baseline")
        self.assertIsNone(first["readBytesPerSecond"])
        # Ten process ticks out of 100 machine ticks is 10% of total machine
        # capacity, matching btop with proc_per_core disabled.
        self.assertEqual(second["cpuPercent"], 10.0)
        self.assertEqual(second["readBytesPerSecond"], 100)
        self.assertEqual(second["writeBytesPerSecond"], 150)

    def test_unreadable_cpu_and_io_are_unknown_not_zero(self) -> None:
        rows = [
            {
                "id": "7:10",
                "pid": 7,
                "cpuTicks": 10,
                "memoryBytes": 50,
                "threads": 2,
            }
        ]
        sampler = ActivitySampler()

        metrics = sampler.sample(ProcFs(Path("/missing")), rows, now=1.0)

        self.assertIsNone(metrics["cpuPercent"])
        self.assertFalse(metrics["cpuAvailable"])
        self.assertIsNone(metrics["readBytesPerSecond"])
        self.assertFalse(metrics["ioAvailable"])
        self.assertIsNone(rows[0]["cpuPercent"])
        self.assertIsNone(rows[0]["readBytesPerSecond"])
        self.assertEqual(len(sampler.last_limited), 2)


if __name__ == "__main__":
    unittest.main()
