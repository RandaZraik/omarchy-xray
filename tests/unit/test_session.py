from datetime import datetime, timedelta, timezone
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from xray.session import InspectionSession
from xray.targets.query import TargetSpec
from xray.targets.resolver import ResolutionInventory, ResolvedTarget


def resolved(kind: str = "process", pid: int = 41) -> ResolvedTarget:
    return ResolvedTarget(
        TargetSpec(kind, "demo.service" if kind == "service" else str(pid), "Demo"),
        pid,
        pid,
        {},
        [],
        [],
        {},
    )


def refresh_session(target: ResolvedTarget) -> InspectionSession:
    session = object.__new__(InspectionSession)
    session.resolved = target
    session.snapshot = {
        "context": {},
        "metrics": {},
        "processes": [],
        "target": {"kind": target.spec.kind, "rootPid": target.root_pid},
    }
    session.sampling_paused = False
    session.settings = SimpleNamespace(capture_preview=True, history_seconds=60)
    session._resolved_at = time.monotonic()
    session._inspection_id = 1
    session.resolver = MagicMock()
    session.resolver.inventory.return_value = ResolutionInventory([], {})
    session.history = MagicMock()
    session.history.track.return_value = ({}, [])
    session.collector = MagicMock()
    session.collector.resource_revision = 1
    return session


class SessionTests(unittest.TestCase):
    def test_focus_process_rejects_boolean_and_non_positive_pids(self) -> None:
        session = object.__new__(InspectionSession)
        for value in (True, False, 0, -1, "0", "-1", "not-a-pid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                session.focus_process(value)

    def test_collect_requires_a_resolved_target_even_with_optimized_python(
        self,
    ) -> None:
        session = object.__new__(InspectionSession)
        session.resolved = None

        with self.assertRaisesRegex(ValueError, "choose a target"):
            session._collect()

    def test_focused_inspection_rejects_a_hidden_workspace_client(self) -> None:
        session = object.__new__(InspectionSession)
        session.settings = SimpleNamespace(capture_preview=False)
        session.resolver = MagicMock()
        session.resolver.inventory.return_value = ResolutionInventory(
            windows=[
                {
                    "address": "0xhidden",
                    "pid": 41,
                    "focused": True,
                    "workspace": {"id": 1},
                }
            ],
            parents={41: 1},
            visible_workspaces=frozenset({2}),
        )
        session._inspect_spec = MagicMock()

        self.assertEqual(session.inspect_focused(), {})
        session.resolver.inventory.assert_called_once()
        self.assertTrue(
            session.resolver.inventory.call_args.kwargs["include_visibility"]
        )
        session._inspect_spec.assert_not_called()

    def test_preview_is_retained_only_for_the_same_window_address(self) -> None:
        session = refresh_session(resolved())
        session.snapshot["context"] = {
            "window": {"address": "0xold"},
            "previewPath": "/tmp/old-preview.png",
        }
        session._resolved_identity_matches = MagicMock(return_value=True)
        session._collect = MagicMock(
            return_value={
                "context": {"window": {"address": "0xnew"}},
                "metrics": {},
            }
        )

        snapshot = session.refresh()

        self.assertNotIn("previewPath", snapshot["context"])

    def test_compact_refresh_returns_only_changed_top_level_domains(self) -> None:
        session = refresh_session(resolved())
        session.settings.capture_preview = False
        session.snapshot.update(
            {
                "metrics": {"cpuPercent": 1},
                "files": [{"fd": 1}],
                "changes": {},
                "timeline": [],
            }
        )
        session._resolved_identity_matches = MagicMock(return_value=True)
        session._collect = MagicMock(
            return_value={
                **session.snapshot,
                "metrics": {"cpuPercent": 2},
                "generatedAt": "new",
            }
        )

        response = session.refresh(compact=True)

        self.assertEqual(
            response["snapshotPatch"],
            {"metrics": {"cpuPercent": 2}, "generatedAt": "new"},
        )
        session._collect.assert_called_once_with(None, refresh_resources=False)
        session.history.track.assert_called_once_with(
            session.snapshot,
            ("connections", "files", "pipewire", "inhibitors", "runtime"),
        )

    def test_recycled_numeric_pid_forces_a_fresh_target_session(self) -> None:
        session = refresh_session(resolved())
        replacement = resolved()
        session._resolved_identity_matches = MagicMock(return_value=False)
        session.resolver.resolve_with_inventory.return_value = replacement
        session._inspect_spec = MagicMock(return_value={"fresh": True})

        self.assertEqual(session.refresh(), {"fresh": True})
        session._inspect_spec.assert_called_once_with(
            replacement.spec,
            session.resolver.inventory.return_value,
            replacement,
        )

    def test_empty_managed_target_is_resolved_again_when_it_reappears(self) -> None:
        session = refresh_session(resolved("service", 0))
        replacement = resolved("service", 42)
        session._resolved_identity_matches = MagicMock(return_value=False)
        session.resolver.resolve_with_inventory.return_value = replacement
        session._inspect_spec = MagicMock(return_value={"rootPid": 42})

        self.assertEqual(session.refresh(), {"rootPid": 42})
        session._inspect_spec.assert_called_once()

    def test_paused_refresh_returns_the_persisted_current_settings(self) -> None:
        session = refresh_session(resolved())
        session.sampling_paused = True
        session.snapshot["settings"] = {"refreshSeconds": 2}
        session.settings = SimpleNamespace(
            capture_preview=False,
            history_seconds=60,
            as_dict=lambda: {"refreshSeconds": 10},
        )

        paused = session.refresh()

        self.assertEqual(paused["settings"], {"refreshSeconds": 10})
        self.assertEqual(session.snapshot["settings"], {"refreshSeconds": 2})

    def test_sampling_pause_updates_the_snapshot_and_resets_rate_baselines(
        self,
    ) -> None:
        session = refresh_session(resolved())
        session.collector = MagicMock()

        paused = session.set_sampling_paused(True)

        self.assertEqual(paused, {"samplingPaused": True})
        self.assertTrue(session.snapshot["samplingPaused"])
        session.collector.reset_sampling_baselines.assert_called_once_with()

        session.set_sampling_paused(True)
        session.collector.reset_sampling_baselines.assert_called_once_with()

        session.set_sampling_paused(False)
        self.assertFalse(session.snapshot["samplingPaused"])
        self.assertEqual(session.collector.reset_sampling_baselines.call_count, 2)

    def test_sampling_pause_rejects_missing_or_non_boolean_values(self) -> None:
        session = refresh_session(resolved())

        for value in (None, 0, 1, "true", {}, []):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "paused must be a boolean"),
            ):
                session.set_sampling_paused(value)

    def test_stable_application_refresh_avoids_global_rediscovery(self) -> None:
        session = refresh_session(resolved("application"))
        session._resolved_at = 0
        session._resolved_identity_matches = MagicMock(return_value=True)
        session._collect = MagicMock(return_value=dict(session.snapshot))

        session.refresh(compact=True)

        session.resolver.inventory.assert_not_called()
        session._collect.assert_called_once_with(None, refresh_resources=False)

    def test_history_window_uses_the_saved_duration(self) -> None:
        session = object.__new__(InspectionSession)
        session.settings = SimpleNamespace(history_seconds=60)
        now = datetime.now(timezone.utc)
        events = [
            {"timestamp": (now - timedelta(seconds=90)).isoformat(), "id": "old"},
            {"timestamp": (now - timedelta(seconds=10)).isoformat(), "id": "new"},
        ]

        self.assertEqual(
            [event["id"] for event in session._timeline_window(events)], ["new"]
        )

    def test_destructive_action_revalidates_resource_ownership(self) -> None:
        session = refresh_session(resolved("port", 41))
        session.snapshot["processes"] = [{"pid": 41, "startTime": 100, "uid": 1000}]
        session.actions = MagicMock()
        session._resolved_identity_matches = MagicMock(return_value=True)
        session.resolver.resolve_with_inventory.return_value = resolved("port", 0)

        result = session.perform_action("terminate", 1)

        self.assertFalse(result["ok"])
        self.assertIn("selected process changed", result["message"])
        session.actions.perform.assert_not_called()

    def test_relaunch_rejects_a_recycled_root_or_changed_manager(self) -> None:
        session = refresh_session(resolved("process", 41))
        session.snapshot["processes"] = [{"pid": 41, "startTime": 100, "uid": 1000}]
        session.snapshot["context"] = {"container": {"id": "old", "runtime": "docker"}}
        session.actions = MagicMock()

        session._resolved_identity_matches = MagicMock(return_value=False)
        recycled = session.perform_action("relaunch", 1)
        self.assertFalse(recycled["ok"])
        self.assertIn("process changed", recycled["message"])

        session._resolved_identity_matches.return_value = True
        session.resolver.resolve_with_inventory.return_value = session.resolved
        session._collect = MagicMock(
            return_value={"context": {"container": {"id": "new", "runtime": "docker"}}}
        )
        changed = session.perform_action("relaunch", 1)
        self.assertFalse(changed["ok"])
        self.assertIn("manager changed", changed["message"])
        session.actions.perform.assert_not_called()

    def test_action_is_rejected_when_the_visible_inspection_changed(self) -> None:
        session = refresh_session(resolved())
        session.snapshot["processes"] = [{"pid": 41, "startTime": 100, "uid": 1000}]
        session.actions = MagicMock()

        result = session.perform_action("terminate", 0)

        self.assertFalse(result["ok"])
        self.assertIn("target changed", result["message"])
        session.actions.perform.assert_not_called()


if __name__ == "__main__":
    unittest.main()
