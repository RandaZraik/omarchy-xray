from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from xray.system.descriptors import Descriptor, collect_descriptors, read_stable_fdinfo
from xray.system.procfs import ProcFs, ReadResult


class DescriptorInventoryTests(unittest.TestCase):
    def test_inventory_reads_each_descriptor_once_and_enforces_total_budget(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for pid in (10, 11):
                (root / f"{pid}/fd").mkdir(parents=True)
                for fd in range(3):
                    (root / f"{pid}/fd/{fd}").symlink_to(f"/tmp/{pid}-{fd}")
            inventory = collect_descriptors(
                ProcFs(root), [10, 11], limit_per_process=3, total_limit=4
            )

        self.assertEqual(len(inventory.records), 4)
        self.assertEqual(
            [(row.pid, row.fd) for row in inventory.records],
            [(10, 0), (10, 1), (10, 2), (11, 0)],
        )
        self.assertIn("Descriptors are limited to 4 total entries", inventory.limited)

    def test_inventory_reports_per_process_truncation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "10/fd").mkdir(parents=True)
            for fd in range(3):
                (root / f"10/fd/{fd}").symlink_to(f"/tmp/{fd}")
            inventory = collect_descriptors(
                ProcFs(root), [10], limit_per_process=2, total_limit=10
            )

        self.assertEqual(len(inventory.records), 2)
        self.assertIn("Process 10 descriptors are limited to 2", inventory.limited)

    def test_inventory_declares_directory_and_target_read_failures(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "10").mkdir()
            (root / "11/fd").mkdir(parents=True)
            (root / "11/fd/3").symlink_to("/tmp/missing")
            inventory = collect_descriptors(ProcFs(root), [10, 11])

        self.assertIn(10, inventory.unavailable_pids)
        self.assertTrue(
            any(
                "Process 10 descriptors are unavailable" in row
                for row in inventory.limited
            )
        )

    def test_fdinfo_is_rejected_when_the_descriptor_target_changes(self) -> None:
        proc = MagicMock()
        proc.path.return_value.stat.side_effect = [
            SimpleNamespace(st_dev=1, st_ino=2),
            SimpleNamespace(st_dev=1, st_ino=2),
        ]
        proc.readlink.side_effect = [
            ReadResult("/tmp/before"),
            ReadResult("/tmp/after"),
        ]
        proc.read.return_value = ReadResult("pos:\t0\nflags:\t0\n")

        result = read_stable_fdinfo(
            proc, Descriptor(41, 3, "3", "/tmp/before", 1, 2), limit=1024
        )

        self.assertFalse(result.available)
        self.assertIn("changed", result.error)


if __name__ == "__main__":
    unittest.main()
