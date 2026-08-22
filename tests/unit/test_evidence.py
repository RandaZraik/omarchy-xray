import unittest

from xray.evidence.changes import EvidenceHistory, compare_snapshots
from xray.evidence.explanations import derive_explanations


def snapshot(
    processes=(),
    connections=(),
    files=(),
    locks=(),
    devices=(),
    gpu_devices=(),
    inhibitors=(),
    cpu=0,
    memory=0,
    gpu=0,
    limited=(),
):
    return {
        "processes": list(processes),
        "connections": list(connections),
        "files": list(files),
        "locks": list(locks),
        "devices": {
            "pipewire": list(devices),
            "gpu": list(gpu_devices),
            "inhibitors": list(inhibitors),
        },
        "metrics": {"cpuPercent": cpu, "memoryBytes": memory, "gpuPercent": gpu},
        "coverage": {"limited": list(limited)},
        "security": {},
        "context": {},
        "logs": [],
    }


class EvidenceTests(unittest.TestCase):
    def test_baseline_counts_additions_removals_and_metric_deltas(self) -> None:
        before = snapshot(processes=[{"id": "1:1"}], cpu=2, memory=10)
        after = snapshot(processes=[{"id": "2:2"}], cpu=5, memory=25)
        changes = compare_snapshots(before, after)
        self.assertEqual(changes["domains"]["processes"], {"added": 1, "removed": 1})
        self.assertEqual(changes["metrics"]["memoryBytes"], 15.0)

    def test_all_device_domains_participate_in_change_tracking(self) -> None:
        before = snapshot()
        after = snapshot(
            gpu_devices=[{"pid": 1, "device": "/dev/dri/renderD128", "clientId": "7"}],
            inhibitors=[{"pid": 1, "what": "sleep", "mode": "block"}],
        )
        self.assertEqual(
            compare_snapshots(before, after)["domains"]["devices"],
            {"added": 2, "removed": 0},
        )

    def test_service_container_and_cause_changes_participate_in_history(self) -> None:
        before = snapshot()
        after = snapshot()
        after["context"] = {
            "service": {"id": "demo.service", "scope": "user", "activeState": "active"},
            "container": {"id": "abc", "runtime": "docker", "state": "running"},
            "cause": {"nodes": [{"id": "unit:user:demo.service"}]},
        }
        self.assertEqual(
            compare_snapshots(before, after)["domains"]["runtime"],
            {"added": 3, "removed": 0},
        )

    def test_history_resets_for_a_new_target_and_records_events(self) -> None:
        history = EvidenceHistory()
        first = snapshot(files=[])
        history.reset(first)
        _, events = history.track(
            snapshot(files=[{"pid": 1, "fd": 3, "target": "/tmp/a"}])
        )
        self.assertEqual(events[0]["label"], "1 file added")
        history.reset(first)
        self.assertEqual(history.events, [])

    def test_history_reuses_only_explicitly_stable_domain_fingerprints(self) -> None:
        history = EvidenceHistory()
        first = snapshot(
            files=[{"pid": 1, "fd": 3, "target": "/tmp/a"}],
            gpu_devices=[{"pid": 1, "device": "renderD128", "clientId": "1"}],
        )
        history.reset(first)
        changed = snapshot(
            files=[{"pid": 1, "fd": 4, "target": "/tmp/b"}],
            gpu_devices=[{"pid": 1, "device": "renderD128", "clientId": "2"}],
        )

        changes, _events = history.track(changed, ("files",))

        self.assertEqual(changes["domains"]["files"], {"added": 0, "removed": 0})
        self.assertEqual(changes["domains"]["devices"], {"added": 1, "removed": 1})

    def test_kernel_lock_changes_participate_in_file_history(self) -> None:
        before = snapshot()
        after = snapshot(
            locks=[
                {
                    "owner": "OFD",
                    "type": "OFDLCK",
                    "mode": "Write",
                    "inode": "00:08:9",
                    "start": "0",
                    "end": "EOF",
                }
            ]
        )

        self.assertEqual(
            compare_snapshots(before, after)["domains"]["files"],
            {"added": 1, "removed": 0},
        )

    def test_unavailable_metrics_and_domains_do_not_create_false_changes(self) -> None:
        history = EvidenceHistory()
        first = snapshot(devices=[{"pid": 1, "id": 2, "active": True}], cpu=None)
        first["coverage"]["domains"] = {"devices": "available"}
        history.reset(first)

        unavailable = snapshot(cpu=None)
        unavailable["devices"]["availability"] = {"pipewire": "unavailable"}
        unavailable["coverage"]["domains"] = {"devices": "unavailable"}
        changes, events = history.track(unavailable)
        self.assertEqual(changes["domains"]["devices"], {"added": 0, "removed": 0})
        self.assertIsNone(changes["metrics"]["cpuPercent"])
        self.assertEqual(events, [])

        direct = compare_snapshots(first, unavailable)
        self.assertEqual(
            direct["domains"]["devices"],
            {"added": 0, "removed": 0, "status": "unavailable"},
        )

        recovered = snapshot(devices=[{"pid": 1, "id": 2, "active": True}], cpu=5)
        recovered["coverage"]["domains"] = {"devices": "available"}
        changes, events = history.track(recovered)
        self.assertEqual(changes["domains"]["devices"], {"added": 0, "removed": 0})
        self.assertEqual(events, [])

    def test_one_failed_device_source_does_not_hide_other_proven_changes(self) -> None:
        history = EvidenceHistory()
        before = snapshot(devices=[{"pid": 1, "id": 2, "active": True}])
        before["coverage"]["domains"] = {
            "pipewire": "available",
            "gpu": "available",
            "inhibitors": "available",
        }
        history.reset(before)
        after = snapshot(
            gpu_devices=[{"pid": 3, "device": "/dev/dri/renderD128", "clientId": "7"}]
        )
        after["coverage"]["domains"] = {
            "pipewire": "unavailable",
            "gpu": "available",
            "inhibitors": "available",
        }

        changes, events = history.track(after)

        self.assertEqual(changes["domains"]["devices"]["added"], 1)
        self.assertEqual(changes["domains"]["devices"]["removed"], 0)
        self.assertEqual(events[0]["label"], "1 device added")
        self.assertEqual(
            compare_snapshots(before, after)["domains"]["devices"]["status"],
            "partial",
        )

    def test_explanations_are_direct_and_cover_privacy_and_limits(self) -> None:
        data = snapshot(
            connections=[{"externallyReachable": True, "localPort": 8000}],
            files=[{"deleted": True}],
            devices=[{"active": True, "kind": "microphone", "name": "WebRTC"}],
            limited=["maps denied"],
        )
        titles = [row["title"] for row in derive_explanations(data)]
        self.assertEqual(
            titles,
            [
                "Listening beyond localhost",
                "Deleted files are still held open",
                "Microphone capture is active",
                "Some information is unavailable",
            ],
        )

    def test_explanations_abstain_when_no_supported_conclusion_is_proven(self) -> None:
        rows = derive_explanations(snapshot())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "No alerts")
        self.assertIn("does not guarantee", rows[0]["nextStep"])

    def test_audio_and_generic_video_capture_are_privacy_findings(self) -> None:
        rows = derive_explanations(
            snapshot(
                devices=[
                    {"pid": 1, "id": 2, "active": True, "kind": "audio-capture"},
                    {"pid": 1, "id": 3, "active": True, "kind": "video"},
                ]
            )
        )

        self.assertEqual(
            [row["title"] for row in rows],
            ["Audio-Capture capture is active", "Video capture is active"],
        )

    def test_every_supported_rule_cites_direct_proof_and_a_next_step(self) -> None:
        data = snapshot()
        data.update(
            {
                "locks": [{"pid": 7, "type": "POSIX", "mode": "WRITE", "inode": 9}],
                "security": {"capabilities": ["NET_ADMIN"]},
                "context": {
                    "container": {
                        "id": "abc",
                        "name": "demo",
                        "runtime": "docker",
                        "privileged": True,
                    }
                },
                "logs": [{"priority": "3", "message": "Known failure"}],
            }
        )
        rows = derive_explanations(data)
        identifiers = {row["id"] for row in rows}
        self.assertEqual(
            identifiers,
            {
                "file-locks",
                "effective-capabilities",
                "privileged-container",
                "journal-errors",
            },
        )
        self.assertTrue(all(row["evidence"] for row in rows))
        self.assertTrue(all(row["nextStep"] for row in rows))
        self.assertTrue(all(row["status"] == "Found" for row in rows))


if __name__ == "__main__":
    unittest.main()
