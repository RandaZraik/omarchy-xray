from __future__ import annotations

from pathlib import Path

from xray.capsules.archive import (
    compare_capsule,
    default_export_directory,
    export_capsule,
    load_capsule,
)
from xray.evidence.redaction import redact_snapshot


class CapsuleService:
    """Read, write, compare, and summarize privacy-safe inspection capsules."""

    @staticmethod
    def export(snapshot: dict[str, object], directory: object = None) -> dict[str, str]:
        destination = (
            Path(str(directory)).expanduser()
            if directory
            else default_export_directory()
        )
        return {"path": str(export_capsule(snapshot, destination))}

    @staticmethod
    def open(path: object) -> dict[str, object]:
        return load_capsule(Path(str(path)))

    @staticmethod
    def compare(snapshot: dict[str, object], path: object) -> dict[str, object]:
        return compare_capsule(snapshot, CapsuleService.open(path))

    @staticmethod
    def report(snapshot: dict[str, object]) -> dict[str, str]:
        sanitized = redact_snapshot(snapshot)
        target = sanitized.get("target", {})
        metrics = sanitized.get("metrics", {})
        explanations = sanitized.get("explanations", [])

        def percent(value: object) -> str:
            return "unavailable" if value is None else f"{value}%"

        lines = [
            f"Omarchy X-Ray — {target.get('label', 'Inspection')}",
            f"PID: {target.get('rootPid', '—')}",
            (
                f"Processes: {metrics.get('processCount', 0)} · "
                f"CPU: {percent(metrics.get('cpuPercent'))} · "
                f"Memory: {metrics.get('memoryBytes', 0)} bytes · "
                f"GPU: {percent(metrics.get('gpuPercent'))}"
            ),
            "",
            "What stands out:",
        ]
        lines.extend(
            f"- {row.get('title')}: {row.get('why')}"
            for row in explanations
            if isinstance(row, dict)
        )
        network = sanitized.get("network", {})
        if isinstance(network, dict) and network.get("flows"):
            totals = network.get("totals", {})
            lines.extend(
                [
                    "",
                    "Network connections:",
                    f"Source: {'IP packet bytes' if network.get('mode') == 'packets' else 'TCP payload bytes'}",
                    f"Observed totals: {totals.get('sentBytes', 0)} bytes uploaded; {totals.get('receivedBytes', 0)} bytes downloaded",
                ]
            )
            for flow in network["flows"]:
                if flow.get("listening"):
                    continue
                owners = ", ".join(
                    f"{owner.get('name', 'Process')} (PID {owner.get('pid')})"
                    for owner in flow.get("owners", [])
                )
                lines.append(
                    f"- {owners} → {flow.get('remoteAddress')}:{flow.get('remotePort')} ({flow.get('protocol')}, {flow.get('sampleStatus')})"
                )
            lines.extend(
                f"Limited: {message}" for message in network.get("limited", [])
            )
        performance = sanitized.get("performance", {})
        checks = performance.get("checks", []) if isinstance(performance, dict) else []
        if checks:
            lines.extend(["", "Why slow?", str(performance.get("summary", ""))])
            for check in checks:
                lines.append(
                    f"- [{check.get('status', 'Unavailable')}] {check.get('title', 'Check')}"
                )
                lines.append(f"  {check.get('why', '')}")
                lines.extend(f"  {value}" for value in check.get("evidence", []))
                if check.get("nextStep"):
                    lines.append(f"  Next: {check['nextStep']}")
        return {"text": "\n".join(lines)}
