from __future__ import annotations

from collections import deque
from typing import Iterable

from xray.config import LIMITS, TIMING
from xray.system.commands import CommandRunner


def _integer(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(props: dict[str, object]) -> str:
    return " ".join(
        str(props.get(key, ""))
        for key in (
            "media.class",
            "media.role",
            "node.role",
            "media.name",
            "node.description",
            "node.name",
            "device.api",
        )
    ).lower()


def _source_kind(props: dict[str, object]) -> str:
    media_class = str(props.get("media.class", ""))
    value = _text(props)
    if any(token in value for token in ("screen", "screencast", "screen-cast")):
        return "screen"
    if media_class == "Video/Source" and (
        any(token in value for token in ("camera", "webcam", "v4l2"))
        or str(props.get("device.api", "")).lower() == "v4l2"
    ):
        return "camera"
    if media_class == "Video/Source":
        return "video"
    if media_class == "Audio/Source" and not any(
        token in value for token in ("monitor", "virtual")
    ):
        return "microphone"
    if media_class.startswith("Audio/"):
        return "audio"
    return "other"


def _stream_kind(
    props: dict[str, object], linked_sources: list[dict[str, object]]
) -> str:
    media_class = str(props.get("media.class", ""))
    value = _text(props)
    if media_class == "Stream/Input/Audio":
        return (
            "microphone"
            if any(_source_kind(source) == "microphone" for source in linked_sources)
            else "audio-capture"
        )
    if media_class == "Stream/Input/Video":
        source_kinds = {_source_kind(source) for source in linked_sources}
        if "screen" in source_kinds or any(
            token in value for token in ("screen", "screencast", "screen-cast")
        ):
            return "screen"
        if "camera" in source_kinds or any(
            token in value for token in ("camera", "webcam")
        ):
            return "camera"
        return "video"
    if media_class == "Stream/Output/Audio":
        return "audio"
    if media_class == "Stream/Output/Video":
        return "video"
    return "other"


def _parse_pipewire_dump(
    payload: object,
) -> tuple[list[dict[str, object]], bool]:
    if not isinstance(payload, list):
        return [], False
    client_props: dict[int, dict[str, object]] = {}
    nodes: dict[int, dict[str, object]] = {}
    active_links: list[tuple[int, int]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        props = info.get("props") if isinstance(info.get("props"), dict) else {}
        item_type = str(item.get("type", ""))
        if item_type.endswith(":Client"):
            client_props[_integer(item.get("id"))] = props
            continue
        if item_type.endswith(":Node"):
            nodes[_integer(item.get("id"))] = props
            continue
        if not item_type.endswith(":Link"):
            continue
        if str(info.get("state", "")).lower() not in {"active", "running"}:
            continue
        output_node = _integer(props.get("link.output.node"))
        input_node = _integer(props.get("link.input.node"))
        if output_node > 0 and input_node > 0:
            active_links.append((output_node, input_node))

    adjacency: dict[int, set[int]] = {}
    for output_node, input_node in active_links:
        adjacency.setdefault(output_node, set()).add(input_node)
        adjacency.setdefault(input_node, set()).add(output_node)

    graph_truncated = False

    def linked_nodes(start: int) -> list[int]:
        nonlocal graph_truncated
        result: list[int] = []
        seen = {start}
        queue = deque(sorted(adjacency.get(start, set())))
        while queue and len(seen) < LIMITS.pipewire_graph_nodes:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            result.append(current)
            queue.extend(sorted(adjacency.get(current, set()) - seen))
        if queue:
            graph_truncated = True
        return result

    rows: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict) or not str(item.get("type", "")).endswith(
            ":Node"
        ):
            continue
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        props = info.get("props") if isinstance(info.get("props"), dict) else {}
        owner = client_props.get(_integer(props.get("client.id")), {})
        pid = _integer(
            props.get("application.process.id") or owner.get("application.process.id")
        )
        if pid <= 0:
            continue
        node_id = _integer(item.get("id"))
        media_class = str(props.get("media.class", ""))
        if not media_class.startswith("Stream/"):
            continue
        role = str(props.get("media.role", props.get("node.role", "")))
        name = str(
            props.get(
                "media.name", props.get("node.description", props.get("node.name", ""))
            )
        )
        state = str(info.get("state", "unknown")).title()
        linked_ids = linked_nodes(node_id)
        linked_sources = [nodes[linked] for linked in linked_ids if linked in nodes]
        source_ids = sorted(
            linked
            for linked in linked_ids
            if linked in nodes
            and str(nodes[linked].get("media.class", "")).endswith("/Source")
        )
        rows.append(
            {
                # PipeWire object IDs are reusable after a node disappears. The
                # serial is the stable identity for history when the server
                # provides it; old servers still fall back to the node ID.
                "id": _integer(props.get("object.serial")) or node_id,
                "pid": pid,
                "kind": _stream_kind(props, linked_sources),
                "name": name or media_class or f"PipeWire node {node_id}",
                "application": str(
                    props.get("application.name")
                    or props.get("application.process.binary")
                    or owner.get("application.name")
                    or owner.get("application.process.binary", "")
                ),
                "mediaClass": media_class,
                "role": role,
                "state": state,
                "source": next(
                    (
                        str(source.get("node.description") or source.get("node.name"))
                        for source in linked_sources
                        if source.get("node.description") or source.get("node.name")
                    ),
                    "",
                ),
                "sourceIds": source_ids,
                "active": str(info.get("state", "")).lower() in {"running", "active"},
            }
        )
    rows.sort(
        key=lambda row: (not bool(row["active"]), str(row["kind"]), str(row["name"]))
    )
    return rows, graph_truncated


def parse_pipewire_dump(payload: object) -> list[dict[str, object]]:
    return _parse_pipewire_dump(payload)[0]


def collect_pipewire(
    runner: CommandRunner, pids: Iterable[int] | None = None
) -> tuple[list[dict[str, object]], str]:
    result = runner.run(["pw-dump"], timeout_seconds=TIMING.slower_command_seconds)
    if result.returncode != 0:
        return [], "PipeWire activity is unavailable"
    payload, valid = result.json_payload()
    if not valid or not isinstance(payload, list):
        return [], "PipeWire activity is unavailable"
    rows, graph_truncated = _parse_pipewire_dump(payload)
    if pids is not None:
        selected = set(pids)
        rows = [row for row in rows if int(row["pid"]) in selected]
    return (
        rows,
        f"PipeWire source graph is limited to {LIMITS.pipewire_graph_nodes} linked nodes"
        if graph_truncated
        else "",
    )


def owners_for_device(rows: list[dict[str, object]], kind: str) -> list[int]:
    if kind == "gpu":
        return []
    kinds = {"microphone", "audio", "audio-capture"} if kind == "audio" else {kind}
    return sorted(
        {int(row["pid"]) for row in rows if row["kind"] in kinds and row["active"]}
    )
