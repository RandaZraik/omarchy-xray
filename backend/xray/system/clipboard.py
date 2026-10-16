"""One explicit paste, outside the shared shell's Qt clipboard reader."""

from __future__ import annotations

import signal

from xray.config import LIMITS, TIMING
from xray.system.commands import CommandRunner


def read_clipboard(*, primary: bool = False) -> dict[str, str]:
    # This watchdog survives destruction of the QML-owned Python helper.
    argv = [
        "timeout",
        "--signal=KILL",
        f"{TIMING.clipboard_seconds}s",
        "wl-paste",
        "--no-newline",
        "--type",
        "text",
    ]
    if primary:
        argv.append("--primary")
    result = CommandRunner().run(
        argv,
        timeout_seconds=TIMING.clipboard_seconds,
        output_limit_bytes=LIMITS.clipboard_bytes,
    )
    if result.unavailable:
        return {"error": "Paste needs GNU coreutils (timeout) installed."}
    if result.returncode in (126, 127):
        return {"error": "Paste needs a working wl-clipboard installation."}
    if result.timed_out or result.returncode in (
        124,
        -signal.SIGKILL,
        128 + signal.SIGKILL,
    ):
        return {"error": "Clipboard did not respond. Try copying again."}
    if result.output_limited:
        return {"error": "Clipboard text is too large (16 KiB maximum)."}
    if result.returncode == 125:
        return {"error": "Clipboard timeout failed. Check the coreutils installation."}
    if result.returncode:
        return {"error": "No clipboard text available."}
    return {"text": result.stdout}
