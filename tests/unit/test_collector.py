from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from xray.config import COVERAGE_DOMAINS
from xray.inspection.collector import SnapshotCollector
from xray.inspection.resources import (
    ConnectionEvidence,
    DeviceEvidence,
    FileEvidence,
    ResourceEvidence,
    RuntimeEvidence,
)
from xray.processes.collector import ProcessCollection
from xray.processes.identity import ProcessIdentity
from xray.system.descriptors import DescriptorInventory
from xray.system.procfs import ProcFs
from xray.targets.query import TargetSpec
from xray.targets.resolver import ResolvedTarget


class SnapshotCollectorTests(unittest.TestCase):
    def collector(self) -> SnapshotCollector:
        return SnapshotCollector(
            ProcFs(Path("/missing")),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )

    def test_empty_snapshot_does_not_claim_no_owner_when_resolution_was_limited(
        self,
    ) -> None:
        resolved = ResolvedTarget(
            TargetSpec("port", "8080", "Port 8080"),
            0,
            0,
            {},
            [],
            [],
            {},
            "No matching process could be found because required system data is unavailable",
            ("TCP table is permission-limited",),
        )

        snapshot = self.collector().empty_snapshot(resolved, {}, False)

        self.assertEqual(snapshot["coverage"]["status"], "Some data unavailable")
        self.assertEqual(
            snapshot["coverage"]["limited"], ["TCP table is permission-limited"]
        )
        self.assertEqual(snapshot["coverage"]["statusCode"], "limited")
        self.assertEqual(
            snapshot["coverage"]["domains"],
            {name: "unavailable" for name in COVERAGE_DOMAINS},
        )

    def test_unavailable_or_invalid_uptime_is_unknown_and_explained(self) -> None:
        collector = self.collector()

        missing, missing_reason = collector.proc.process_uptime_seconds(100)
        self.assertIsNone(missing)
        self.assertIn("unavailable", missing_reason)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "uptime").write_text("not-a-counter", encoding="utf-8")
            invalid, invalid_reason = ProcFs(root).process_uptime_seconds(100)
        self.assertIsNone(invalid)
        self.assertIn("invalid system counters", invalid_reason)

    def test_descendant_churn_keeps_root_evidence_and_marks_processes_limited(
        self,
    ) -> None:
        collector = self.collector()
        identity = ProcessIdentity(41, 100, 1000)
        rows = [
            {
                "id": "41:100",
                "pid": 41,
                "ppid": 1,
                "startTime": 100,
                "uid": 1000,
                "name": "root",
                "state": "S",
            },
            {
                "id": "42:200",
                "pid": 42,
                "ppid": 41,
                "startTime": 200,
                "uid": 1000,
                "name": "child",
                "state": "S",
            },
        ]
        tree = ProcessCollection(identity, rows, [])
        evidence = ResourceEvidence(
            process_identities=(identity, ProcessIdentity(42, 200, 1000)),
            collected_at=1.0,
            descriptors=DescriptorInventory((), ()),
            connections=ConnectionEvidence([], ()),
            files=FileEvidence([], [], (), True, True),
            devices=DeviceEvidence([], "", [], ""),
            runtime=RuntimeEvidence(
                {"previewEligible": False, "window": {}, "cause": {"nodes": []}},
                (),
                (),
                {},
                (),
                (),
                "",
            ),
        )
        collector.resources = MagicMock()
        collector.resources.collect.return_value = evidence
        collector.activity = MagicMock()
        collector.activity.sample.return_value = {
            "processCount": 2,
            "cpuPercent": None,
        }
        collector.activity.last_limited = []
        collector.gpu = MagicMock()
        collector.gpu.sample.return_value = None
        collector.actions.catalog.return_value = []
        collector.proc.process_uptime_seconds = MagicMock(return_value=(1, ""))
        collector._changed_identities = MagicMock(return_value=[42])
        target = ResolvedTarget(
            TargetSpec("process", "41", "Process 41"),
            41,
            41,
            {},
            [],
            [],
            {},
        )

        with (
            patch("xray.inspection.collector.collect_tree", return_value=tree),
            patch(
                "xray.inspection.collector.collect_gpu_clients",
                return_value=([], []),
            ),
        ):
            snapshot = collector.collect(target, {}, False)

        self.assertEqual(snapshot["target"]["rootPid"], 41)
        self.assertEqual(snapshot["target"]["query"], "pid:41")
        self.assertEqual([row["pid"] for row in snapshot["processes"]], [41, 42])
        self.assertEqual(snapshot["coverage"]["domains"]["processes"], "limited")
        self.assertTrue(
            any(
                "child processes changed" in reason
                for reason in snapshot["coverage"]["limited"]
            )
        )


if __name__ == "__main__":
    unittest.main()
