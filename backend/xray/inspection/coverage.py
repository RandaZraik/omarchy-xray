from __future__ import annotations

from xray.inspection.resources import ResourceEvidence
from xray.processes.collector import ProcessCollection
from xray.targets.resolver import ResolvedTarget


def build_coverage(
    *,
    resolved: ResolvedTarget,
    tree: ProcessCollection,
    context: dict[str, object],
    resources: ResourceEvidence,
    activity_limited: list[str],
    uptime_limited: str,
    gpu_clients: list[dict[str, object]],
    gpu_limited: list[str],
) -> tuple[dict[str, object], dict[str, str]]:
    connection_limited = list(resources.connections.limited)
    file_limited = list(resources.files.limited)
    context_limited = list(resources.runtime.context_limited)
    runtime_limited = list(resources.runtime.limited)
    security_limited = list(resources.runtime.security_limited)
    limited = list(
        dict.fromkeys(
            [
                *tree.limited,
                *([uptime_limited] if uptime_limited else []),
                *activity_limited,
                *connection_limited,
                *file_limited,
                *gpu_limited,
                *context_limited,
                *runtime_limited,
                *security_limited,
                *resolved.limited,
                *(
                    [resources.devices.pipewire_error]
                    if resources.devices.pipewire_error
                    else []
                ),
                *(
                    [resources.devices.inhibitor_error]
                    if resources.devices.inhibitor_error
                    else []
                ),
                *(
                    [resources.runtime.logs_limited]
                    if resources.runtime.logs_limited
                    else []
                ),
            ]
        )
    )
    availability = {
        "pipewire": (
            "partial"
            if resources.devices.pipewire_error and resources.devices.pipewire
            else "unavailable"
            if resources.devices.pipewire_error
            else "available"
        ),
        "gpu": (
            "partial"
            if gpu_limited and gpu_clients
            else "unavailable"
            if gpu_limited
            else "available"
        ),
        "inhibitors": "unavailable"
        if resources.devices.inhibitor_error
        else "available",
    }
    device_domains = {
        name: "limited" if status == "partial" else status
        for name, status in availability.items()
    }
    statuses = tuple(device_domains.values())
    devices_status = (
        "available"
        if all(status == "available" for status in statuses)
        else "unavailable"
        if all(status == "unavailable" for status in statuses)
        else "limited"
    )
    available = [
        "Process tree and activity",
        "Open files and locks" if resources.files.locks_available else "Open files",
        "Network sockets",
        "Runtime and security",
        "Application context",
    ]
    if not resources.devices.pipewire_error or resources.devices.pipewire:
        available.append("PipeWire devices")
    if not resources.devices.inhibitor_error:
        available.append("Sleep inhibitors")
    if not resources.runtime.logs_limited:
        available.append("Journal entries")
    if gpu_clients or not gpu_limited:
        available.append("DRM GPU clients")
    cause = context.get("cause", {})
    if isinstance(cause, dict) and cause.get("nodes"):
        available.append("How the app started")
    if context.get("container"):
        available.append("Container runtime context")
    return (
        {
            "statusCode": "limited" if limited else "full",
            "status": "Some data unavailable" if limited else "All data available",
            "available": available,
            "limited": limited,
            "domains": {
                "processes": "limited" if tree.topology_limited else "available",
                "connections": "limited" if connection_limited else "available",
                "files": (
                    "available"
                    if resources.files.files_complete
                    and resources.files.locks_available
                    else "limited"
                ),
                **device_domains,
                "devices": devices_status,
                "runtime": (
                    "limited"
                    if context_limited
                    or runtime_limited
                    or security_limited
                    or resources.runtime.logs_limited
                    else "available"
                ),
            },
        },
        availability,
    )
