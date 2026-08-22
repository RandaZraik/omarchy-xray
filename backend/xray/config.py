from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Limits:
    process_tree: int = 512
    ancestry_depth: int = 128
    query_matches: int = 20
    query_bytes: int = 4096
    descriptors_per_process: int = 2048
    descriptors_total: int = 32_768
    file_rows: int = 12_000
    mapped_libraries: int = 300
    journal_entries: int = 50
    journal_processes: int = 64
    timeline_events: int = 240
    catalog_processes: int = 400
    catalog_services: int = 160
    catalog_containers: int = 80
    catalog_ports: int = 100
    catalog_bytes: int = 4 * 1024 * 1024
    catalog_domain_bytes: int = 512 * 1024
    catalog_string_bytes: int = 4096
    network_namespaces: int = 16
    socket_table_bytes: int = 256 * 1024
    cause_nodes: int = 24
    capsule_bytes: int = 16 * 1024 * 1024
    capsule_json_bytes: int = 4 * 1024 * 1024
    capsule_nodes: int = 200_000
    capsule_depth: int = 32
    capsule_string_bytes: int = 262_144
    command_output_bytes: int = 8 * 1024 * 1024
    response_bytes: int = 16 * 1024 * 1024
    snapshot_bytes: int = 14 * 1024 * 1024
    process_command_bytes: int = 64 * 1024
    process_command_arguments: int = 256
    process_environment_bytes: int = 64 * 1024
    process_environment_names: int = 256
    pipewire_graph_nodes: int = 128
    git_metadata_bytes: int = 4096
    active_launchers: int = 16
    runtime_detail_cache_entries: int = 256
    package_owner_cache_entries: int = 256


@dataclass(frozen=True)
class Timing:
    command_seconds: float = 2.0
    slower_command_seconds: float = 3.0
    manager_restart_seconds: float = 30.0
    journal_refresh_seconds: float = 10.0
    security_refresh_seconds: float = 10.0
    process_metadata_refresh_seconds: float = 10.0
    resource_refresh_seconds: float = 5.0
    target_resolution_seconds: float = 5.0
    runtime_catalog_refresh_seconds: float = 10.0
    process_exit_seconds: float = 2.0
    window_pick_seconds: float = 60.0
    window_focus_seconds: float = 0.5
    window_focus_poll_seconds: float = 0.02
    stale_preview_seconds: float = 24 * 60 * 60


LIMITS = Limits()
TIMING = Timing()
STATE_DIRECTORY = "omarchy-xray"
CAPSULE_SCHEMA = 1
COVERAGE_DOMAINS: Final[tuple[str, ...]] = (
    "processes",
    "connections",
    "files",
    "pipewire",
    "gpu",
    "inhibitors",
    "devices",
    "runtime",
)

SETTINGS_SPEC: Final[tuple[dict[str, object], ...]] = (
    {
        "key": "refreshSeconds",
        "type": "choice",
        "label": "Refresh live data",
        "description": "How often X-Ray updates the selected app while it is open.",
        "default": 2,
        "options": (
            {"value": 1, "label": "Every second"},
            {"value": 2, "label": "Every 2 seconds"},
            {"value": 5, "label": "Every 5 seconds"},
            {"value": 10, "label": "Every 10 seconds"},
        ),
    },
    {
        "key": "historySeconds",
        "type": "choice",
        "label": "Timeline window",
        "description": "Keep recent process and activity changes visible for this long.",
        "default": 300,
        "options": (
            {"value": 60, "label": "1 minute"},
            {"value": 300, "label": "5 minutes"},
            {"value": 900, "label": "15 minutes"},
        ),
    },
    {
        "key": "capturePreview",
        "type": "boolean",
        "label": "Window preview",
        "description": "Capture the selected window before opening X-Ray. This adds a short opening delay; previews are never exported.",
        "default": False,
    },
)


def settings_defaults() -> dict[str, object]:
    return {str(setting["key"]): setting["default"] for setting in SETTINGS_SPEC}


def settings_contract() -> list[dict[str, object]]:
    return [
        {**setting, "options": [dict(option) for option in setting.get("options", ())]}
        for setting in SETTINGS_SPEC
    ]


def normalize_settings(candidate: object) -> dict[str, object]:
    source = candidate if isinstance(candidate, dict) else {}
    normalized = settings_defaults()
    for setting in SETTINGS_SPEC:
        key = str(setting["key"])
        if setting["type"] == "boolean":
            if isinstance(source.get(key), bool):
                normalized[key] = source[key]
            continue
        allowed = tuple(option["value"] for option in setting.get("options", ()))
        value = source.get(key)
        if not isinstance(value, bool) and value in allowed:
            normalized[key] = value
    return normalized
