from __future__ import annotations

import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from live_backend import LiveBackend, wait_until
from window_oracle import QML_EXECUTABLE, mapped_window

from xray.actions.desktop import DesktopEvidence
from xray.actions.process_control import ProcessActions
from xray.processes.identity import identity_for
from xray.runtime.context import list_windows
from xray.system.commands import CommandRunner
from xray.system.hyprland import (
    focus_window,
    visible_workspace_evidence,
    window_workspace_id,
)
from xray.system.procfs import ProcFs
from xray.targets.query import TargetSpec
from xray.targets.resolver import TargetResolver


HAS_HYPRLAND = bool(
    os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl")
)


@unittest.skipUnless(HAS_HYPRLAND, "requires a live Hyprland session")
class HyprlandTruthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proc = ProcFs()
        self.runner = CommandRunner()
        self.actions = ProcessActions(self.proc, self.runner)

    def controllable_window(self) -> dict[str, object]:
        windows, error = list_windows(self.runner)
        self.assertEqual(error, "")
        for window in windows:
            identity = identity_for(self.proc, int(window["pid"]))
            if identity and self.actions.guard.validate(identity)[0]:
                return window
        self.skipTest("no independent same-user window is available")

    def test_focus_action_matches_hyprlands_active_window_oracle(self) -> None:
        if not QML_EXECUTABLE:
            self.skipTest("qml6 or qml is required for deterministic focus testing")
        with mapped_window(self.runner, label="focus target") as window:
            with mapped_window(self.runner, label="focus decoy") as decoy:
                self.assertNotEqual(window["address"], decoy["address"])
                identity = identity_for(self.proc, int(window["pid"]))
                assert identity
                result = self.actions.perform("focus", identity, {"window": window})
                self.assertTrue(result.ok, result.message)

                def focused() -> bool:
                    response = self.runner.run(["hyprctl", "-j", "activewindow"])
                    if response.returncode != 0:
                        return False
                    return (
                        str(response.json({}).get("address", "")) == window["address"]
                    )

                self.assertTrue(
                    wait_until(focused),
                    f"Hyprland did not focus {window['address']}",
                )

    def test_focused_inspection_resolves_the_controlled_active_window(self) -> None:
        if not QML_EXECUTABLE:
            self.skipTest("qml6 or qml is required for deterministic focus testing")
        with mapped_window(self.runner, label="focused inspection") as window:
            self.assertTrue(focus_window(self.runner, window["address"]))
            with (
                TemporaryDirectory() as state_home,
                LiveBackend(Path(state_home)) as backend,
            ):
                response = backend.request("inspectFocused")
                self.assertTrue(response["ok"], response)
                snapshot = response["data"]
            self.assertEqual(
                snapshot["context"]["window"]["address"], window["address"]
            )
            self.assertEqual(snapshot["target"]["ownerPid"], window["pid"])

    def test_exact_window_query_preserves_hyprlands_window_identity(self) -> None:
        window = self.controllable_window()
        with TemporaryDirectory() as state_home:
            with LiveBackend(Path(state_home)) as backend:
                response = backend.request(
                    "inspect", query=f"window:{window['address']}"
                )
                self.assertTrue(response["ok"], response)
                snapshot = response["data"]
        self.assertEqual(snapshot["target"]["ownerPid"], window["pid"])
        self.assertEqual(snapshot["context"]["window"]["address"], window["address"])
        self.assertEqual(snapshot["context"]["window"]["title"], window["title"])

    def test_exact_window_never_drifts_to_a_same_process_sibling_workspace(
        self,
    ) -> None:
        windows, error = list_windows(self.runner)
        self.assertEqual(error, "")
        selected = None
        for window in windows:
            siblings = [
                candidate
                for candidate in windows
                if candidate["pid"] == window["pid"]
                and candidate["address"] != window["address"]
                and candidate.get("workspace") != window.get("workspace")
            ]
            identity = identity_for(self.proc, int(window["pid"]))
            if siblings and identity and self.actions.guard.validate(identity)[0]:
                selected = next(
                    (
                        candidate
                        for candidate in [window, *siblings]
                        if not candidate["focused"]
                    ),
                    window,
                )
                break
        if not selected:
            self.skipTest(
                "no same-process windows on different workspaces are available"
            )

        with TemporaryDirectory() as state_home:
            with LiveBackend(Path(state_home)) as backend:
                response = backend.request(
                    "inspect", query=f"window:{selected['address']}"
                )
                self.assertTrue(response["ok"], response)
                actual = response["data"]["context"]["window"]
        self.assertEqual(actual["address"], selected["address"])
        self.assertEqual(actual["workspace"], selected["workspace"])
        self.assertEqual(actual["title"], selected["title"])

    def test_point_picker_resolves_the_visible_window_not_hidden_overlap(
        self,
    ) -> None:
        if not QML_EXECUTABLE:
            self.skipTest("qml6 or qml is required for deterministic picker testing")
        with mapped_window(self.runner, label="point picker anchor") as anchor:
            windows, error = list_windows(self.runner)
            self.assertEqual(error, "")
            visible, visibility_error = visible_workspace_evidence(self.runner)
            self.assertEqual(visibility_error, "")
            candidates = [
                window
                for window in windows
                if window.get("mapped", True)
                and not window.get("hidden", False)
                and window_workspace_id(window) in visible
                and int(window["width"]) > 0
                and int(window["height"]) > 0
            ]
            point = (
                int(anchor["x"]) + max(1, int(anchor["width"]) // 2),
                int(anchor["y"]) + max(1, int(anchor["height"]) // 2),
            )
            overlaps = [
                window
                for window in candidates
                if int(window["x"])
                <= point[0]
                < int(window["x"]) + int(window["width"])
                and int(window["y"])
                <= point[1]
                < int(window["y"]) + int(window["height"])
            ]
            self.assertTrue(overlaps)
            selected = min(
                overlaps,
                key=lambda window: (
                    not bool(window.get("focused")),
                    int(window.get("focusOrder", 1_000_000)),
                ),
            )
            resolver = TargetResolver(self.proc, self.runner)
            resolved = resolver.resolve(
                TargetSpec("window-point", f"{point[0]},{point[1]}", "Picked window")
            )
            self.assertEqual(resolved.window["address"], selected["address"])
            self.assertEqual(resolved.window["workspace"], selected["workspace"])

    def test_hidden_workspace_preview_never_changes_the_visible_workspace(
        self,
    ) -> None:
        windows, error = list_windows(self.runner)
        self.assertEqual(error, "")
        visible, visibility_error = visible_workspace_evidence(self.runner)
        self.assertEqual(visibility_error, "")
        hidden = next(
            (
                window
                for window in windows
                if window_workspace_id(window)
                and window_workspace_id(window) not in visible
            ),
            None,
        )
        if not hidden:
            self.skipTest("no window is currently parked on a hidden workspace")

        hidden_workspace = window_workspace_id(hidden)
        self.assertNotIn(hidden_workspace, visible)
        with TemporaryDirectory() as state_home:
            with LiveBackend(Path(state_home)) as backend:
                inspected = backend.request(
                    "inspect", query=f"window:{hidden['address']}"
                )
                self.assertTrue(inspected["ok"], inspected)
                self.assertFalse(inspected["data"]["context"]["previewEligible"])
                captured = backend.request("capturePreview")
                self.assertTrue(captured["ok"], captured)
                self.assertEqual(captured["data"]["previewPath"], "")

        after_monitors = self.runner.run(["hyprctl", "-j", "monitors"]).json([])
        after_active = self.runner.run(["hyprctl", "-j", "activewindow"]).json({})
        active_workspaces = {
            int((monitor.get("activeWorkspace") or {}).get("id", 0))
            for monitor in after_monitors
        }
        self.assertNotIn(
            hidden_workspace,
            active_workspaces,
            "preview capture made the hidden target's workspace visible",
        )
        self.assertNotEqual(
            str(after_active.get("address", "")).lower(),
            str(hidden.get("address", "")).lower(),
            "preview capture focused the hidden target",
        )

    @unittest.skipUnless(shutil.which("grim"), "requires grim")
    def test_preview_is_a_private_bounded_png_of_the_selected_window(self) -> None:
        if not QML_EXECUTABLE:
            self.skipTest("qml6 or qml is required for deterministic preview testing")
        with mapped_window(self.runner, label="bounded preview") as window:
            desktop = DesktopEvidence(self.runner)
            try:
                capture = desktop.capture_window(window)
                path = Path(capture.path)
                self.assertTrue(path.is_file())
                self.assertGreater(capture.source_width, 0)
                self.assertGreater(capture.source_height, 0)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                data = path.read_bytes()
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                width = int.from_bytes(data[16:20], "big")
                height = int.from_bytes(data[20:24], "big")
                self.assertLessEqual(width, 960)
                self.assertLessEqual(height, 600)
                self.assertAlmostEqual(
                    width / height,
                    capture.source_width / capture.source_height,
                    places=2,
                )
            finally:
                desktop.close()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
