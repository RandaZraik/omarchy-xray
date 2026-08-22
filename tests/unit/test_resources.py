from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from xray.inspection.resources import (
    ConnectionEvidence,
    DeviceEvidence,
    FileEvidence,
    ResourceCollector,
    ResourceEvidence,
    RuntimeEvidence,
)
from xray.processes.collector import ProcessCollection
from xray.processes.identity import ProcessIdentity
from xray.system.descriptors import DescriptorInventory
from xray.system.procfs import ProcFs
from xray.targets.query import TargetSpec
from xray.targets.resolver import ResolvedTarget


class ResourceCollectorTests(unittest.TestCase):
    def collector(self) -> ResourceCollector:
        return ResourceCollector(
            ProcFs(Path("/missing")),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )

    @staticmethod
    def evidence(identity: tuple[int, int, int]) -> ResourceEvidence:
        return ResourceEvidence(
            process_identities=(ProcessIdentity(*identity),),
            collected_at=100.0,
            descriptors=DescriptorInventory((), ()),
            connections=ConnectionEvidence([], ()),
            files=FileEvidence([], [], (), True, True),
            devices=DeviceEvidence([], "", [], ""),
            runtime=RuntimeEvidence({}, (), (), {}, (), (), ""),
        )

    def test_journal_failure_is_retained_as_a_coverage_limitation(self) -> None:
        collector = self.collector()
        with (
            patch(
                "xray.inspection.resources.collect_logs",
                return_value=([], "Journal entries are unavailable"),
            ),
            patch.object(collector.proc, "process_started_at", return_value=(1.0, "")),
        ):
            collector._refresh_logs(
                ProcessIdentity(41, 100, 1000), [41], {"scope": "system"}
            )

        self.assertEqual(collector._logs, [])
        self.assertEqual(collector._logs_limited, "Journal entries are unavailable")
        self.assertEqual(collector._logs_scope, "system")

    def test_compact_refresh_reuses_recent_resource_evidence(self) -> None:
        collector = self.collector()
        cached = self.evidence((41, 100, 1000))
        collector._cached = cached
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
            patch("xray.inspection.resources.time.monotonic", return_value=104.0),
            patch(
                "xray.inspection.resources.collect_descriptors",
                side_effect=AssertionError("resource evidence should be reused"),
            ),
        ):
            reused = collector.collect(
                target,
                ProcessCollection(
                    ProcessIdentity(41, 100, 1000),
                    [{"pid": 41, "startTime": 100, "uid": 1000}],
                    [],
                ),
                None,
                force=False,
            )

        self.assertIs(reused, cached)

    def test_cache_rejects_reused_numeric_pid_with_new_identity(self) -> None:
        collector = self.collector()
        collector._cached = self.evidence((41, 100, 1000))
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
            patch("xray.inspection.resources.time.monotonic", return_value=101.0),
            patch(
                "xray.inspection.resources.collect_descriptors",
                side_effect=RuntimeError("fresh collection required"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "fresh collection required"):
                collector.collect(
                    target,
                    ProcessCollection(
                        ProcessIdentity(41, 101, 1000),
                        [{"pid": 41, "startTime": 101, "uid": 1000}],
                        [],
                    ),
                    None,
                    force=False,
                )


if __name__ == "__main__":
    unittest.main()
