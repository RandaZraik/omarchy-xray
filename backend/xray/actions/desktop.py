from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
import os
from pathlib import Path
import time

from xray.config import STATE_DIRECTORY, TIMING
from xray.runtime.context import revalidate_window
from xray.system.commands import CommandRunner
from xray.system.hyprland import (
    visible_workspace_evidence,
    window_workspace_id,
)


@dataclass(frozen=True)
class PreviewCapture:
    path: str = ""
    error: str = ""
    source_width: int = 0
    source_height: int = 0


class DesktopEvidence:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
        self.directory = runtime / STATE_DIRECTORY
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        stale_before = time.time() - TIMING.stale_preview_seconds
        for path in self.directory.glob("preview-*.png"):
            try:
                if path.stat().st_mtime < stale_before:
                    path.unlink(missing_ok=True)
            except OSError:
                continue
        self._previews: list[Path] = []

    def capture_window(self, window: dict[str, object]) -> PreviewCapture:
        window, target_address, error = revalidate_window(self.runner, window)
        if error:
            return PreviewCapture(error=error)
        geometry, width, height = self._geometry(window)
        if not geometry:
            return PreviewCapture(error="Window geometry is unavailable")
        if target_address:
            error = self._visibility_error(window)
            if error:
                return PreviewCapture(error=error)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        path = self.directory / f"preview-{stamp}.png"
        scale = min(1.0, 960 / width, 600 / height)
        argv = ["grim", "-g", geometry]
        if scale < 1.0:
            argv.extend(["-s", f"{scale:.4f}"])
        result = self.runner.run(
            [*argv, str(path)], timeout_seconds=TIMING.slower_command_seconds
        )
        if result.returncode != 0 or not path.is_file():
            path.unlink(missing_ok=True)
            return PreviewCapture(
                error="Window capture timed out"
                if result.timed_out
                else "Window capture failed"
            )
        path.chmod(0o600)
        self._previews.append(path)
        while len(self._previews) > 3:
            old = self._previews.pop(0)
            old.unlink(missing_ok=True)
        return PreviewCapture(path=str(path), source_width=width, source_height=height)

    @staticmethod
    def _geometry(window: dict[str, object]) -> tuple[str, int, int]:
        try:
            x = int(window.get("x", 0))
            y = int(window.get("y", 0))
            width = int(window.get("width", 0))
            height = int(window.get("height", 0))
        except (TypeError, ValueError):
            return "", 0, 0
        if width <= 0 or height <= 0:
            return "", 0, 0
        return f"{x},{y} {width}x{height}", width, height

    def _visibility_error(self, window: dict[str, object]) -> str:
        if not window.get("mapped", True) or window.get("hidden", False):
            return "The selected window is not currently visible"
        if not window.get("focused", False):
            return "Preview is available only for the focused window"
        target_workspace = window_workspace_id(window)
        if not target_workspace:
            return "The selected window workspace is unavailable"
        visible_workspaces, error = visible_workspace_evidence(self.runner)
        if error:
            return error
        return (
            ""
            if target_workspace in visible_workspaces
            else "The selected window is not visible on an active workspace"
        )

    def clear_previews(self) -> None:
        for path in self._previews:
            path.unlink(missing_ok=True)
        self._previews = []

    def pick_point(self) -> tuple[int, int] | None:
        result = self.runner.run(
            ["slurp", "-p", "-f", "%x %y"], timeout_seconds=TIMING.window_pick_seconds
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.split()
        if len(parts) != 2:
            return None
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None

    def close(self) -> None:
        self.clear_previews()
