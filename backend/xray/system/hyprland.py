from __future__ import annotations

import re
import time

from xray.config import TIMING
from xray.system.commands import CommandRunner


def window_address(value: object) -> str:
    address = str(value or "")
    return address if re.fullmatch(r"0x[0-9a-fA-F]+", address) else ""


def window_workspace_id(window: object) -> int:
    if not isinstance(window, dict):
        return 0
    workspace = window.get("workspace", {})
    if not isinstance(workspace, dict):
        return 0
    try:
        return int(workspace.get("id", 0))
    except (TypeError, ValueError):
        return 0


def visible_workspace_evidence(runner: CommandRunner) -> tuple[set[int], str]:
    result = runner.run(["hyprctl", "-j", "monitors"])
    payload, valid = result.json_payload()
    if not valid or not isinstance(payload, list):
        return set(), result.stderr or "Hyprland monitor visibility is unavailable"
    workspace_ids: set[int] = set()
    for monitor in payload:
        if not isinstance(monitor, dict):
            continue
        for key in ("activeWorkspace", "specialWorkspace"):
            workspace_id = window_workspace_id({"workspace": monitor.get(key, {})})
            if workspace_id:
                workspace_ids.add(workspace_id)
    if not workspace_ids:
        return set(), "Hyprland reported no visible workspace"
    return workspace_ids, ""


def focus_window(runner: CommandRunner, address: object) -> bool:
    normalized = window_address(address)
    if not normalized:
        return False
    selector = f"address:{normalized}"
    result = runner.run(
        [
            "hyprctl",
            "dispatch",
            f'hl.dsp.focus({{ window = "{selector}" }})',
        ]
    )
    if result.returncode == 0 and _wait_for_active_window(runner, normalized):
        return True
    result = runner.run(["hyprctl", "dispatch", "focuswindow", selector])
    return result.returncode == 0 and _wait_for_active_window(runner, normalized)


def _wait_for_active_window(runner: CommandRunner, address: str) -> bool:
    deadline = time.monotonic() + TIMING.window_focus_seconds
    while time.monotonic() < deadline:
        if _active_window_is(runner, address):
            return True
        time.sleep(TIMING.window_focus_poll_seconds)
    return _active_window_is(runner, address)


def _active_window_is(runner: CommandRunner, address: str) -> bool:
    result = runner.run(["hyprctl", "-j", "activewindow"])
    if result.returncode != 0:
        return False
    payload = result.json({})
    return isinstance(payload, dict) and payload.get("address") == address
