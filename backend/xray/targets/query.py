from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from xray.config import LIMITS
from xray.runtime.containers import SUPPORTED_CONTAINER_RUNTIMES


@dataclass(frozen=True)
class TargetSpec:
    kind: str
    value: str
    label: str


def canonical_query(spec: TargetSpec, window_address: object = "") -> str:
    """Return the stable query that reopens a resolved target."""
    kind = spec.kind
    value = spec.value
    if kind == "window-point":
        address = str(window_address or "")
        return f"window:{address}" if address else ""
    if kind == "window":
        return f"window:{value}"
    if kind == "process":
        return f"pid:{value}"
    if kind == "port":
        return f":{value}"
    if kind in {"service", "container"}:
        return f"{kind}:{value}"
    if kind == "catalog":
        return ""
    return value


def match_score(needle: str, values: object) -> int:
    normalized = needle.casefold()
    scores = (
        (
            100
            if value == normalized
            else 60
            if value.startswith(normalized)
            else 30
            if normalized in value
            else 0
        )
        for raw in values
        if (value := str(raw).casefold())
    )
    return max(scores, default=0)


def rank_services(
    rows: list[dict[str, object]], query: str, scope: str = ""
) -> list[dict[str, object]]:
    scored = (
        (
            match_score(query, (row.get("id", ""), row.get("description", ""))),
            row,
        )
        for row in rows
        if not scope or row.get("scope") == scope
    )
    return [
        row
        for score, row in sorted(
            (item for item in scored if item[0]),
            key=lambda item: (-item[0], str(item[1].get("id", ""))),
        )
    ][: LIMITS.query_matches]


def rank_containers(
    rows: list[dict[str, object]], query: str
) -> list[dict[str, object]]:
    keys = ("name", "id", "shortId", "image", "composeProject", "composeService")
    scored = (
        (match_score(query, (row.get(key, "") for key in keys)), row) for row in rows
    )
    return [
        row
        for score, row in sorted(
            (item for item in scored if item[0]),
            key=lambda item: (-item[0], str(item[1].get("name", ""))),
        )
    ][: LIMITS.query_matches]


DEVICE_TARGETS = (
    ("Microphone", "microphone", "Microphone activity", ("mic",)),
    ("Camera", "camera", "Camera activity", ("webcam",)),
    ("Audio", "audio", "Audio activity", ()),
    ("GPU", "gpu", "GPU activity", ()),
)

_RESOURCE_ALIASES = {
    alias: ("device", query, description)
    for _label, query, description, extra_aliases in DEVICE_TARGETS
    for alias in (query, *extra_aliases)
}


def quick_targets() -> list[dict[str, str]]:
    return [
        {"label": label, "query": query}
        for label, query, _description, _aliases in DEVICE_TARGETS
    ]


def service_selector(value: str) -> tuple[str, str]:
    scope, separator, query = value.partition(":")
    if separator and scope.casefold() in {"user", "system"}:
        return scope.casefold(), query
    return "", value


def container_selector(value: str) -> tuple[str, str]:
    runtime, separator, query = value.partition(":")
    if separator and runtime.casefold() in SUPPORTED_CONTAINER_RUNTIMES:
        return runtime.casefold(), query
    return "", value


def parse_query(raw: object, home: Path | None = None) -> TargetSpec:
    text = str(raw or "").strip()
    if len(text.encode("utf-8")) > LIMITS.query_bytes:
        raise ValueError("query exceeds the size limit")
    lower = text.lower()
    if not text:
        return TargetSpec("catalog", "", "Running applications and resources")

    if lower in _RESOURCE_ALIASES:
        kind, value, label = _RESOURCE_ALIASES[lower]
        return TargetSpec(kind, value, label)

    window_match = re.fullmatch(r"window\s*:\s*(0x[0-9a-f]+)", lower)
    if window_match:
        address = window_match.group(1)
        return TargetSpec("window", address, "Selected window")

    pid_match = re.fullmatch(r"(?:pid\s*:\s*)?(\d+)", lower)
    if pid_match:
        pid = pid_match.group(1)
        return TargetSpec("process", pid, f"Process {pid}")

    port_match = re.fullmatch(r"(?:(?:port)?\s*:\s*)(\d{1,5})", lower)
    if port_match:
        port = int(port_match.group(1))
        if 0 < port <= 65535:
            return TargetSpec("port", str(port), f"Port {port}")

    explicit_port = re.fullmatch(r"port\s+(\d{1,5})", lower)
    if explicit_port:
        port = int(explicit_port.group(1))
        if 0 < port <= 65535:
            return TargetSpec("port", str(port), f"Port {port}")

    service_match = re.fullmatch(r"service\s*:\s*(.+)", text, re.IGNORECASE)
    if service_match:
        value = service_match.group(1).strip()
        if value:
            scope, query = service_selector(value)
            if scope and not query:
                return TargetSpec("application", text, text)
            label = f"{scope.title()} service {query}" if scope else f"Service {query}"
            return TargetSpec("service", value, label)

    container_match = re.fullmatch(r"container\s*:\s*(.+)", text, re.IGNORECASE)
    if container_match:
        value = container_match.group(1).strip()
        if value:
            runtime, query = container_selector(value)
            if runtime and not query:
                return TargetSpec("application", text, text)
            label = (
                f"{runtime.title()} container {query}"
                if runtime
                else f"Container {query}"
            )
            return TargetSpec("container", value, label)

    file_value = text[5:].strip() if lower.startswith("file:") else text
    if file_value.startswith(("/", "~/", "./", "../")):
        base = home or Path.home()
        path = Path(file_value.replace("~", str(base), 1)).expanduser()
        return TargetSpec("file", str(path), path.name or str(path))

    return TargetSpec("application", text, text)
