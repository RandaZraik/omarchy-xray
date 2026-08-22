from __future__ import annotations

import os
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from xray.actions.desktop import DesktopEvidence
from xray.system.commands import CommandResult


class FakeRunner:
    def __init__(self, results: list[CommandResult] | None = None) -> None:
        self.results = list(results or [])
        self.calls: list[list[str]] = []

    def run(self, argv, **_kwargs):
        normalized = [str(value) for value in argv]
        self.calls.append(normalized)
        if normalized[0] == "grim":
            Path(normalized[-1]).write_bytes(b"\x89PNG\r\n\x1a\n")
            return CommandResult(tuple(normalized), 0, "", "")
        if self.results:
            return self.results.pop(0)
        return CommandResult(tuple(normalized), 0, "", "")


class DesktopEvidenceTests(unittest.TestCase):
    @staticmethod
    def focused_window_results(
        *, x: int = 10, y: int = 20, width: int = 640, height: int = 480
    ) -> list[CommandResult]:
        return [
            CommandResult(
                ("hyprctl",),
                0,
                json.dumps(
                    [
                        {
                            "address": "0xdef",
                            "pid": 41,
                            "at": [x, y],
                            "size": [width, height],
                            "workspace": {"id": 2},
                            "focusHistoryID": 0,
                        }
                    ]
                ),
                "",
            ),
            CommandResult(
                ("hyprctl",),
                0,
                '[{"activeWorkspace":{"id":2},"specialWorkspace":{"id":0}}]',
                "",
            ),
        ]

    @staticmethod
    def focused_window() -> dict[str, object]:
        return {
            "address": "0xdef",
            "pid": 41,
            "workspace": {"id": 2},
            "focused": True,
            "mapped": True,
            "hidden": False,
        }

    def test_startup_removes_only_stale_xray_previews(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}),
        ):
            runtime = Path(directory) / "omarchy-xray"
            runtime.mkdir(mode=0o755)
            stale = runtime / "preview-previous.png"
            active = runtime / "preview-active.png"
            unrelated = runtime / "keep-me.txt"
            stale.write_bytes(b"old")
            active.write_bytes(b"current")
            os.utime(stale, (0, 0))
            unrelated.write_bytes(b"mine")

            desktop = DesktopEvidence(FakeRunner())

            self.assertFalse(stale.exists())
            self.assertTrue(active.exists())
            self.assertTrue(unrelated.exists())
            self.assertEqual(runtime.stat().st_mode & 0o777, 0o700)
            desktop.close()

    def test_a_second_backend_never_deletes_an_active_preview(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}),
        ):
            first = DesktopEvidence(
                FakeRunner(self.focused_window_results(width=30, height=20, x=1, y=2))
            )
            path = Path(first.capture_window(self.focused_window()).path)
            second = DesktopEvidence(FakeRunner())

            self.assertTrue(path.is_file())
            second.close()
            self.assertTrue(path.is_file())
            first.close()
            self.assertFalse(path.exists())

    def test_picker_accepts_only_an_exact_coordinate_pair(self) -> None:
        successful = FakeRunner([CommandResult(("slurp",), 0, "120 340\n", "")])
        invalid = FakeRunner([CommandResult(("slurp",), 0, "120,340\n", "")])
        cancelled = FakeRunner([CommandResult(("slurp",), 1, "", "cancelled")])
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}),
        ):
            self.assertEqual(DesktopEvidence(successful).pick_point(), (120, 340))
            self.assertIsNone(DesktopEvidence(invalid).pick_point())
            self.assertIsNone(DesktopEvidence(cancelled).pick_point())

    def test_previews_are_private_bounded_and_cleaned_on_close(self) -> None:
        runner = FakeRunner(self.focused_window_results() * 4)
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}),
        ):
            desktop = DesktopEvidence(runner)
            paths = [
                Path(desktop.capture_window(self.focused_window()).path)
                for _ in range(4)
            ]
            self.assertFalse(paths[0].exists())
            self.assertTrue(paths[1].is_file())
            self.assertTrue(paths[2].is_file())
            self.assertTrue(paths[3].is_file())
            self.assertEqual(paths[3].stat().st_mode & 0o777, 0o600)
            grim = next(call for call in reversed(runner.calls) if call[0] == "grim")
            self.assertEqual(grim[1:3], ["-g", "10,20 640x480"])
            desktop.close()
            self.assertFalse(paths[1].exists())
            self.assertFalse(paths[2].exists())
            self.assertFalse(paths[3].exists())

    def test_invalid_preview_geometry_never_invokes_grim(self) -> None:
        runner = FakeRunner()
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}),
        ):
            desktop = DesktopEvidence(runner)
            capture = desktop.capture_window({})
            self.assertEqual(capture.path, "")
            self.assertIn("identity", capture.error)
            self.assertEqual(runner.calls, [])

    def test_unfocused_window_is_never_screen_captured(self) -> None:
        clients = CommandResult(
            ("hyprctl",),
            0,
            '[{"address":"0xdef","pid":41,"at":[1,2],"size":[300,200],"workspace":{"id":2},"focusHistoryID":1}]',
            "",
        )
        monitors = CommandResult(
            ("hyprctl",),
            0,
            '[{"activeWorkspace":{"id":2},"specialWorkspace":{"id":0}}]',
            "",
        )
        runner = FakeRunner([clients, monitors])
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}),
        ):
            desktop = DesktopEvidence(runner)
            capture = desktop.capture_window(
                {
                    "address": "0xdef",
                    "pid": 41,
                    "x": 1,
                    "y": 2,
                    "width": 300,
                    "height": 200,
                }
            )

            self.assertEqual(capture.path, "")
            self.assertIn("focused window", capture.error)
            self.assertEqual(runner.calls, [["hyprctl", "-j", "clients"]])
            self.assertFalse(any("dispatch" in call for call in runner.calls))
            desktop.close()

    def test_focused_visible_window_is_revalidated_before_capture(self) -> None:
        clients = CommandResult(
            ("hyprctl",),
            0,
            '[{"address":"0xdef","pid":41,"at":[1,2],"size":[300,200],"workspace":{"id":2},"focusHistoryID":0}]',
            "",
        )
        monitors = CommandResult(
            ("hyprctl",),
            0,
            '[{"activeWorkspace":{"id":2},"specialWorkspace":{"id":0}}]',
            "",
        )
        runner = FakeRunner([clients, monitors])
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}),
        ):
            desktop = DesktopEvidence(runner)
            capture = desktop.capture_window(
                {
                    "address": "0xdef",
                    "pid": 41,
                    "focused": True,
                    "workspace": {"id": 2},
                    "x": 1,
                    "y": 2,
                    "width": 300,
                    "height": 200,
                }
            )

            self.assertTrue(Path(capture.path).is_file())
            self.assertEqual(
                runner.calls,
                [
                    ["hyprctl", "-j", "clients"],
                    ["hyprctl", "-j", "monitors"],
                    ["grim", "-g", "1,2 300x200", str(capture.path)],
                ],
            )
            desktop.close()

    def test_hidden_workspace_preview_never_changes_focus(self) -> None:
        monitors = CommandResult(
            ("hyprctl",),
            0,
            '[{"activeWorkspace":{"id":2},"specialWorkspace":{"id":0}}]',
            "",
        )
        clients = CommandResult(
            ("hyprctl",),
            0,
            '[{"address":"0xdef","pid":41,"at":[1,2],"size":[300,200],"workspace":{"id":1},"focusHistoryID":0}]',
            "",
        )
        runner = FakeRunner([clients, monitors])
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}),
        ):
            desktop = DesktopEvidence(runner)
            capture = desktop.capture_window(
                {
                    "address": "0xdef",
                    "pid": 41,
                    "workspace": {"id": 1},
                    "x": 1,
                    "y": 2,
                    "width": 300,
                    "height": 200,
                }
            )

            self.assertEqual(capture.path, "")
            self.assertIn("not visible", capture.error)
            self.assertEqual(
                runner.calls,
                [["hyprctl", "-j", "clients"], ["hyprctl", "-j", "monitors"]],
            )
            desktop.close()

    def test_reused_window_address_with_a_different_pid_is_never_captured(self) -> None:
        clients = CommandResult(
            ("hyprctl",),
            0,
            '[{"address":"0xdef","pid":99,"at":[1,2],"size":[300,200],"workspace":{"id":2}}]',
            "",
        )
        runner = FakeRunner([clients])
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}),
        ):
            capture = DesktopEvidence(runner).capture_window(
                {"address": "0xdef", "pid": 41, "width": 300, "height": 200}
            )
        self.assertEqual(capture.path, "")
        self.assertFalse(any(call[0] == "grim" for call in runner.calls))


if __name__ == "__main__":
    unittest.main()
