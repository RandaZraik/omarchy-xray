from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
import unittest

from live_backend import LiveBackend, wait_until
from window_oracle import QML_EXECUTABLE, mapped_window

from xray.runtime.context import list_windows
from xray.system.commands import CommandRunner
from xray.system.hyprland import (
    focus_window,
    visible_workspace_evidence,
    window_workspace_id,
)


HAS_PREVIEW_ORACLE = bool(
    os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    and shutil.which("hyprctl")
    and shutil.which("grim")
    and shutil.which("magick")
    and QML_EXECUTABLE
)


@unittest.skipUnless(
    HAS_PREVIEW_ORACLE, "requires Hyprland, QML, grim, and ImageMagick"
)
class PreviewTruthTests(unittest.TestCase):
    def test_preview_pixels_come_from_the_exact_selected_window(self) -> None:
        expected = (18, 184, 134)
        runner = CommandRunner()
        with TemporaryDirectory() as directory:
            preview_path = Path()
            with mapped_window(
                runner,
                label="preview",
                color="#12b886",
            ) as window:
                with LiveBackend(Path(directory) / "state") as backend:
                    configured = backend.request(
                        "configure", settings={"capturePreview": True}
                    )
                    self.assertTrue(configured["ok"], configured)
                    inspected = backend.request(
                        "inspect", query=f"window:{window['address']}"
                    )
                    self.assertTrue(inspected["ok"], inspected)
                    self.assertEqual(
                        inspected["data"]["context"]["window"]["address"],
                        window["address"],
                    )

                    # Preview intentionally refuses hidden or unfocused windows.
                    # Reassert the oracle immediately before capture so unrelated
                    # desktop activity cannot turn a pixel-truth test into a
                    # focus-policy test.
                    def focused_and_visible() -> bool:
                        windows, window_error = list_windows(runner)
                        visible, visibility_error = visible_workspace_evidence(runner)
                        current = next(
                            (
                                item
                                for item in windows
                                if item.get("address") == window["address"]
                            ),
                            {},
                        )
                        return bool(
                            not window_error
                            and not visibility_error
                            and current.get("focused")
                            and window_workspace_id(current) in visible
                        )

                    captured = {"ok": False, "error": "preview was not attempted"}
                    for _attempt in range(3):
                        self.assertTrue(
                            wait_until(
                                lambda: (
                                    focus_window(runner, str(window["address"]))
                                    and focused_and_visible()
                                ),
                                timeout=3.0,
                            )
                        )
                        captured = backend.request("capturePreview")
                        if (
                            captured.get("ok")
                            and captured.get("data", {}).get("previewStatus") == "ready"
                        ):
                            break
                    self.assertTrue(captured["ok"], captured)
                    self.assertEqual(
                        captured["data"]["previewStatus"], "ready", captured
                    )
                    preview_path = Path(captured["data"]["previewPath"])
                    self.assertTrue(preview_path.is_file())
                    identify = runner.run(
                        [
                            "magick",
                            str(preview_path),
                            "-format",
                            "%[pixel:p{320,180}]",
                            "info:",
                        ]
                    )
                    self.assertEqual(identify.returncode, 0, identify.stderr)
                    channels = tuple(
                        int(value) for value in re.findall(r"\d+", identify.stdout)[:3]
                    )
                    self.assertEqual(len(channels), 3, identify.stdout)
                    # The compositor's active color profile can shift screenshot
                    # channels slightly while preserving the oracle color.
                    for actual, wanted in zip(channels, expected, strict=True):
                        self.assertLessEqual(abs(actual - wanted), 20, identify.stdout)
                self.assertFalse(preview_path.exists())


if __name__ == "__main__":
    unittest.main()
