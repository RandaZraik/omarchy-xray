from __future__ import annotations

from xray.config import TIMING
from xray.system.commands import CommandRunner


def parse_inhibitors(payload: object, pids: set[int]) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            pid = int(item.get("pid", item.get("PID", 0)))
        except (TypeError, ValueError):
            continue
        if pid not in pids:
            continue
        rows.append(
            {
                "pid": pid,
                "what": str(item.get("what", item.get("WHAT", ""))),
                "who": str(item.get("who", item.get("WHO", ""))),
                "why": str(item.get("why", item.get("WHY", ""))),
                "mode": str(item.get("mode", item.get("MODE", ""))),
            }
        )
    return rows


def collect_inhibitors(
    runner: CommandRunner, pids: list[int]
) -> tuple[list[dict[str, object]], str]:
    result = runner.run(
        ["systemd-inhibit", "--list", "--json=short"],
        timeout_seconds=TIMING.command_seconds,
    )
    if result.returncode != 0:
        return [], "Sleep-inhibitor activity is unavailable"
    payload, valid = result.json_payload()
    if not valid or not isinstance(payload, list):
        return [], "Sleep-inhibitor activity is unavailable"
    return parse_inhibitors(payload, set(pids)), ""
