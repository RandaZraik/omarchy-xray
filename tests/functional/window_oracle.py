from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
from typing import Iterator
import uuid

from live_backend import wait_until

from xray.runtime.context import list_windows
from xray.system.commands import CommandRunner
from xray.system.hyprland import focus_window


QML_EXECUTABLE = shutil.which("qml6") or shutil.which("qml")


@contextmanager
def mapped_window(
    runner: CommandRunner,
    *,
    label: str,
    color: str = "#121212",
    width: int = 640,
    height: int = 360,
) -> Iterator[dict[str, object]]:
    if not QML_EXECUTABLE:
        raise RuntimeError("qml6 or qml is required for a window oracle")

    title = f"X-Ray {label} oracle {uuid.uuid4()}"
    previous_window = next(
        (item for item in list_windows(runner)[0] if item.get("focused")), {}
    )
    with TemporaryDirectory() as directory:
        qml_path = Path(directory) / "oracle.qml"
        qml_path.write_text(
            "import QtQuick\n"
            "import QtQuick.Window\n"
            "Window {\n"
            "  visible: true\n"
            f"  width: {width}; height: {height}\n"
            f"  title: {json.dumps(title)}\n"
            f"  color: {json.dumps(color)}\n"
            f"  Rectangle {{ anchors.fill: parent; color: {json.dumps(color)} }}\n"
            "}\n",
            encoding="utf-8",
        )
        process = subprocess.Popen(
            [QML_EXECUTABLE, str(qml_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            window: dict[str, object] = {}

            def find_oracle() -> bool:
                nonlocal window
                windows, error = list_windows(runner)
                if error:
                    return False
                window = next(
                    (item for item in windows if item.get("title") == title), {}
                )
                return bool(window)

            if not wait_until(find_oracle, 5.0):
                raise AssertionError(f"the {label} oracle window did not map")

            def focus_oracle() -> bool:
                if not find_oracle():
                    return False
                if window.get("focused"):
                    return True
                return focus_window(runner, str(window["address"]))

            if not wait_until(focus_oracle, 5.0):
                raise AssertionError(f"the {label} oracle window could not be focused")
            if not wait_until(find_oracle, 2.0) or not window.get("focused"):
                raise AssertionError(f"the {label} oracle window did not receive focus")
            # Mapping precedes the first committed frame on Wayland. Let the
            # compositor present the known surface before a pixel oracle uses it.
            time.sleep(0.15)
            yield window
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            previous_address = str(previous_window.get("address", ""))
            if previous_address:
                focus_window(runner, previous_address)
