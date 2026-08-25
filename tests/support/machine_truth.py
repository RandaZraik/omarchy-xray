from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import time

from support.markers import parse_json_marker


QML = shutil.which("qml6") or shutil.which("qml")
DETAIL_ORACLE = Path(__file__).with_name("oracles") / "live_detail_oracle.qml"


def display_bytes(value: object) -> str:
    numeric = max(0.0, float(value or 0))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    index = 0
    while numeric >= 1024 and index < len(units) - 1:
        numeric /= 1024
        index += 1
    if index == 0:
        rendered = str(int(numeric + 0.5))
    else:
        rendered = f"{numeric:.{1 if numeric >= 10 else 2}f}"
    return f"{rendered} {units[index]}"


def display_percent(value: object) -> str:
    if value is None:
        return "—"
    numeric = float(value or 0)
    return f"{numeric:.{1 if numeric < 10 else 0}f}%"


def display_rate(value: object) -> str:
    return "—" if value is None else f"{display_bytes(value)}/s"


def display_duration(value: object) -> str:
    if value is None:
        return "—"
    seconds = max(0, int(float(value) + 0.5))
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def expected_detail_counts(snapshot: dict[str, object]) -> dict[str, int]:
    devices = snapshot["devices"]
    availability = devices.get("availability", {})
    context = snapshot["context"]
    security = snapshot["security"]
    service = context.get("service", {})
    container = context.get("container", {})
    runtime = (
        5
        + bool(security.get("apparmor"))
        + (security.get("oomScore") is not None)
        + bool(context.get("package", {}).get("name"))
        + bool(context.get("git", {}).get("root"))
        + len(security.get("namespaces", {}))
        + len(security.get("limits", ()))
        + len(security.get("libraries", ()))
        + len(snapshot["logs"])
        + len(context.get("launch", {}).get("paths", ()))
    )
    if service.get("id"):
        runtime += (
            2
            + bool(service.get("fragmentPath"))
            + len(service.get("triggeredBy", ()))
            + len(service.get("triggers", ()))
        )
    if container.get("id"):
        runtime += (
            2
            + len(container.get("ports", ()))
            + len(container.get("mounts", ()))
            + len(container.get("networks", ()))
            + bool(container.get("command") or container.get("entrypoint"))
            + bool(container.get("composeProject") or container.get("composeService"))
            + bool(container.get("composeWorkingDirectory"))
        )
    device_limits = sum(
        value is False or value in {"unavailable", "partial"}
        for value in availability.values()
    )
    return {
        "processes": len(snapshot["processes"]),
        "connections": len(snapshot["connections"]),
        "files": len(snapshot["files"]) + len(snapshot["locks"]),
        "devices": len(devices.get("pipewire", ()))
        + len(devices.get("gpu", ()))
        + len(devices.get("inhibitors", ()))
        + device_limits,
        "runtime": runtime,
        "cause": len(context["cause"]["nodes"]),
        "explanations": len(snapshot["explanations"]) + len(snapshot["timeline"]),
        "coverage": len(snapshot["coverage"]["available"])
        + len(snapshot["coverage"]["limited"]),
        "alternatives": len(snapshot["target"]["alternatives"]),
    }


def command_json(argv: list[str]) -> object:
    completed = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=8,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"{' '.join(argv)} failed: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def hyprland_clients() -> list[dict[str, object]]:
    payload = command_json(["hyprctl", "-j", "clients"])
    if not isinstance(payload, list):
        raise AssertionError("hyprctl returned a non-list client inventory")
    return [row for row in payload if isinstance(row, dict)]


def proc_status(pid: int) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in Path(f"/proc/{pid}/status").read_text(errors="replace").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            rows[key] = value.strip()
    return rows


def proc_cgroup_paths(pid: int) -> list[str]:
    paths = []
    for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
        _, unified_separator, unified_path = line.partition("::")
        path = unified_path if unified_separator else line.rpartition(":")[2]
        if path:
            paths.append(path)
    return paths


def proc_stat(pid: int) -> dict[str, object]:
    text = Path(f"/proc/{pid}/stat").read_text(errors="replace").strip()
    opened = text.find("(")
    closed = text.rfind(")")
    if opened < 0 or closed <= opened:
        raise AssertionError(f"invalid /proc/{pid}/stat")
    fields = text[closed + 2 :].split()
    return {
        "pid": int(text[:opened].strip()),
        "name": text[opened + 1 : closed],
        "state": fields[0],
        "ppid": int(fields[1]),
        "startTime": int(fields[19]),
        "cpuTicks": sum(int(value) for value in fields[11:13]),
        "rssBytes": int(fields[21]) * os.sysconf("SC_PAGE_SIZE"),
    }


def descriptor_targets(pid: int) -> dict[int, str]:
    result: dict[int, str] = {}
    try:
        entries = list(Path(f"/proc/{pid}/fd").iterdir())
    except OSError:
        return result
    for entry in entries:
        try:
            result[int(entry.name)] = os.readlink(entry)
        except (OSError, ValueError):
            continue
    return result


def descriptor_info(pid: int, fd: int) -> dict[str, object] | None:
    try:
        values = {
            line.partition(":")[0].strip(): line.partition(":")[2].strip()
            for line in Path(f"/proc/{pid}/fdinfo/{fd}").read_text().splitlines()
            if ":" in line
        }
        flags = values["flags"]
        access = int(flags, 8) & os.O_ACCMODE
    except (KeyError, OSError, ValueError):
        return None
    return {
        "position": int(values.get("pos", "0")),
        "flags": flags,
        "mode": (
            "read/write"
            if access == os.O_RDWR
            else "write"
            if access == os.O_WRONLY
            else "read"
        ),
        "mountId": int(values.get("mnt_id", "0")),
    }


def system_cpu_ticks() -> int:
    fields = Path("/proc/stat").read_text().splitlines()[0].split()
    if not fields or fields[0] != "cpu":
        raise AssertionError("/proc/stat has no aggregate CPU row")
    return sum(int(value) for value in fields[1:9])


def proc_io(pid: int) -> dict[str, int] | None:
    try:
        return {
            key.strip(): int(value.strip())
            for line in Path(f"/proc/{pid}/io").read_text().splitlines()
            for key, separator, value in [line.partition(":")]
            if separator
        }
    except (OSError, ValueError):
        return None


def proc_security(pid: int) -> dict[str, object]:
    status = proc_status(pid)
    namespaces: dict[str, str] = {}
    try:
        namespace_entries = list(Path(f"/proc/{pid}/ns").iterdir())
    except OSError:
        namespace_entries = []
    for entry in namespace_entries:
        try:
            namespaces[entry.name] = os.readlink(entry)
        except OSError:
            continue
    try:
        limits_text = Path(f"/proc/{pid}/limits").read_text(errors="replace")
    except OSError:
        limits_text = ""
    limits: list[dict[str, str]] = []
    for line in limits_text.splitlines()[1:]:
        # The kernel table uses two-or-more spaces between columns. Resource
        # names themselves contain single spaces.
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 3:
            limits.append(
                {
                    "name": parts[0],
                    "soft": parts[1],
                    "hard": parts[2],
                    "unit": parts[3] if len(parts) > 3 else "",
                }
            )
    try:
        map_lines = Path(f"/proc/{pid}/maps").read_text(errors="replace").splitlines()
    except OSError:
        map_lines = []
    libraries: set[str] = set()
    for line in map_lines:
        fields = line.split(maxsplit=5)
        if len(fields) < 6:
            continue
        path = fields[5].removesuffix(" (deleted)")
        file_path = Path(path)
        if path.startswith("/") and (
            any(part in {"lib", "lib32", "lib64", "libx32"} for part in file_path.parts)
            or ".so" in file_path.name
        ):
            libraries.add(path)
    capabilities: list[str] = []
    mask = status.get("CapEff", "0")
    completed = subprocess.run(
        ["capsh", f"--decode={mask}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=8,
        check=False,
    )
    if completed.returncode == 0 and "=" in completed.stdout:
        decoded = completed.stdout.strip().partition("=")[2]
        capabilities = [
            value.removeprefix("cap_").upper() for value in decoded.split(",") if value
        ]

    def optional_int(name: str) -> int | None:
        try:
            return int(Path(f"/proc/{pid}/{name}").read_text().strip())
        except (OSError, ValueError):
            return None

    try:
        apparmor = Path(f"/proc/{pid}/attr/current").read_text(errors="replace").strip()
    except OSError:
        apparmor = ""
    return {
        "uid": int(status["Uid"].split()[0]),
        "gid": int(status["Gid"].split()[0]),
        "groups": [int(value) for value in status.get("Groups", "").split()],
        "noNewPrivileges": status.get("NoNewPrivs") == "1"
        if "NoNewPrivs" in status
        else None,
        "seccomp": {"0": "Disabled", "1": "Strict", "2": "Filtered"}.get(
            status.get("Seccomp", ""), "Unknown"
        ),
        "capabilities": capabilities,
        "capabilitiesKnown": "CapEff" in status,
        "apparmor": apparmor,
        "oomScore": optional_int("oom_score"),
        "oomAdjustment": optional_int("oom_score_adj"),
        "namespaces": namespaces,
        "limits": limits,
        "libraries": sorted(libraries),
    }


def systemd_show(unit: str, scope: str) -> dict[str, object]:
    argv = ["systemctl"]
    if scope == "user":
        argv.append("--user")
    argv.extend(
        [
            "show",
            "--no-pager",
            "--property=Id,Description,MainPID,ControlGroup,LoadState,ActiveState,SubState,FragmentPath,TriggeredBy,Triggers,UnitFileState",
            "--",
            unit,
        ]
    )
    completed = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=8,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.strip())
    values = dict(
        line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line
    )
    return {
        "id": values.get("Id", ""),
        "description": values.get("Description", "") or values.get("Id", ""),
        "scope": scope,
        "mainPid": int(values.get("MainPID", "0")),
        "controlGroup": values.get("ControlGroup", ""),
        "loadState": values.get("LoadState", ""),
        "activeState": values.get("ActiveState", ""),
        "subState": values.get("SubState", ""),
        "fragmentPath": values.get("FragmentPath", ""),
        "unitFileState": values.get("UnitFileState", ""),
        "triggeredBy": values.get("TriggeredBy", "").split(),
        "triggers": values.get("Triggers", "").split(),
    }


def raw_journal_entries(
    pid: int,
    start_ticks: int,
    related_pids: list[int],
    unit: str = "",
    scope: str = "user",
    limit: int = 50,
) -> list[dict[str, str]]:
    uptime = float(Path("/proc/uptime").read_text().split()[0])
    started_at = time.time() - uptime + start_ticks / os.sysconf("SC_CLK_TCK")
    argv = ["journalctl"]
    if scope != "system":
        argv.append("--user")
    selected = list(dict.fromkeys(related_pids))[:64]
    if unit:
        argv.append(f"--{'user-' if scope != 'system' else ''}unit={unit}")
    else:
        for index, selected_pid in enumerate(selected or [pid]):
            if index:
                argv.append("+")
            argv.append(f"_PID={selected_pid}")
    argv.extend(
        [
            f"--since=@{max(0, int(started_at))}",
            "--no-pager",
            "--output=json",
            "--lines",
            str(max(1, min(limit, 200))),
        ]
    )
    completed = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=8,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"{' '.join(argv)} failed: {completed.stderr.strip()}")
    # systemd can emit "Started …" a few milliseconds before the new main
    # process becomes visible in procfs. Retain that boundary event so the
    # caller can distinguish it from an omitted in-lifetime entry.
    threshold = max(0, int(started_at * 1_000_000) - 100_000)
    rows = []
    for line in completed.stdout.splitlines():
        try:
            entry = json.loads(line)
            timestamp = int(entry.get("__REALTIME_TIMESTAMP", 0))
        except (TypeError, ValueError):
            continue
        if timestamp and timestamp < threshold:
            continue
        rows.append(
            {
                "timestamp": str(entry.get("__REALTIME_TIMESTAMP", "")),
                "priority": str(entry.get("PRIORITY", "")),
                "unit": str(
                    entry.get("_SYSTEMD_USER_UNIT", entry.get("_SYSTEMD_UNIT", ""))
                ),
                "message": str(entry.get("MESSAGE", "")),
            }
        )
    return rows


def docker_inspect(identifier: str) -> dict[str, object]:
    payload = command_json(["docker", "container", "inspect", identifier])
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise AssertionError("docker inspect returned no container")
    return payload[0]


def _decode_address(value: str, ipv6: bool) -> str:
    if ipv6:
        raw = bytes.fromhex(value)
        raw = b"".join(
            struct.pack(">I", struct.unpack("<I", raw[index : index + 4])[0])
            for index in range(0, 16, 4)
        )
        return socket.inet_ntop(socket.AF_INET6, raw)
    return socket.inet_ntop(socket.AF_INET, struct.pack("<I", int(value, 16)))


def raw_socket_inventory(
    pids: list[int], descriptors: dict[int, dict[int, str]] | None = None
) -> dict[tuple[object, ...], set[int]]:
    state_names = {
        "01": "Established",
        "02": "Syn sent",
        "03": "Syn received",
        "04": "Fin wait 1",
        "05": "Fin wait 2",
        "06": "Time wait",
        "07": "Closed",
        "08": "Close wait",
        "09": "Last ack",
        "0A": "Listening",
        "0B": "Closing",
    }
    namespaces: dict[str, int] = {}
    socket_owners: dict[tuple[str, int], set[int]] = {}
    for pid in pids:
        try:
            namespace = os.readlink(f"/proc/{pid}/ns/net")
        except OSError:
            continue
        namespaces.setdefault(namespace, pid)
        targets = (descriptors or {}).get(pid)
        for target in (
            targets if targets is not None else descriptor_targets(pid)
        ).values():
            if target.startswith("socket:[") and target.endswith("]"):
                socket_owners.setdefault((namespace, int(target[8:-1])), set()).add(pid)

    result: dict[tuple[object, ...], set[int]] = {}
    for namespace, pid in namespaces.items():
        for table in ("tcp", "tcp6", "udp", "udp6"):
            try:
                lines = Path(f"/proc/{pid}/net/{table}").read_text().splitlines()[1:]
            except OSError:
                continue
            ipv6 = table.endswith("6")
            transport = "TCP" if table.startswith("tcp") else "UDP"
            for line in lines:
                fields = line.split()
                if len(fields) < 10:
                    continue
                local_address, local_port = fields[1].split(":")
                remote_address, remote_port = fields[2].split(":")
                inode = int(fields[9])
                owners = socket_owners.get((namespace, inode), set())
                if not owners:
                    continue
                state = (
                    state_names.get(fields[3].upper(), fields[3].upper())
                    if transport == "TCP"
                    else "Open"
                )
                key = (
                    namespace,
                    inode,
                    transport + ("6" if ipv6 else "4"),
                    _decode_address(local_address, ipv6),
                    int(local_port, 16),
                    _decode_address(remote_address, ipv6),
                    int(remote_port, 16),
                    state,
                )
                result[key] = owners
    return result


def raw_locks() -> set[tuple[str, str, str, int, str, str, str]]:
    rows: set[tuple[str, str, str, int, str, str, str]] = set()
    for line in Path("/proc/locks").read_text().splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[4].lstrip("-").isdigit():
            rows.add(
                (
                    fields[1],
                    fields[2],
                    fields[3].title(),
                    int(fields[4]),
                    fields[5],
                    fields[6],
                    fields[7],
                )
            )
    return rows


def raw_drm_clients(
    pids: list[int], descriptors: dict[int, dict[int, str]] | None = None
) -> set[tuple[int, str, str]]:
    return set(raw_drm_details(pids, descriptors))


def raw_drm_details(
    pids: list[int],
    descriptors: dict[int, dict[int, str]] | None = None,
) -> dict[tuple[int, str, str], dict[str, object]]:
    factors = {
        "": 1,
        "b": 1,
        "kb": 1000,
        "kib": 1024,
        "mb": 1_000_000,
        "mib": 1_048_576,
        "gb": 1_000_000_000,
        "gib": 1_073_741_824,
        "tb": 1_000_000_000_000,
        "tib": 1_099_511_627_776,
    }
    result: dict[tuple[int, str, str], dict[str, object]] = {}
    for pid in pids:
        targets = (descriptors or {}).get(pid)
        for fd, target in (
            targets if targets is not None else descriptor_targets(pid)
        ).items():
            if not target.startswith("/dev/dri/"):
                continue
            try:
                lines = Path(f"/proc/{pid}/fdinfo/{fd}").read_text().splitlines()
            except OSError:
                continue
            client = ""
            engines: dict[str, int] = {}
            capacity: dict[str, int] = {}
            memory: dict[str, dict[str, int]] = {
                "memory": {},
                "resident": {},
                "total": {},
            }
            for line in lines:
                key, separator, raw_value = line.partition(":")
                if not separator:
                    continue
                value = raw_value.strip()
                if key == "drm-client-id":
                    client = value
                elif key.startswith("drm-engine-capacity-"):
                    try:
                        capacity[key.removeprefix("drm-engine-capacity-")] = max(
                            1, int(value)
                        )
                    except ValueError:
                        continue
                elif key.startswith("drm-engine-"):
                    fields = value.split()
                    try:
                        if len(fields) == 2 and fields[1] == "ns":
                            engines[key.removeprefix("drm-engine-")] = int(fields[0])
                    except ValueError:
                        continue
                else:
                    match = re.fullmatch(r"drm-(memory|resident|total)-(.+)", key)
                    fields = value.split()
                    if not match or not fields:
                        continue
                    try:
                        unit = fields[1].lower() if len(fields) > 1 else ""
                        memory[match.group(1)][match.group(2)] = int(
                            fields[0]
                        ) * factors.get(unit, 1)
                    except ValueError:
                        continue
            if not client:
                continue
            selected = memory["resident"] or memory["total"] or memory["memory"]
            result[(pid, target, client)] = {
                "engines": engines,
                "capacity": capacity,
                "memory": selected,
                "memoryKind": (
                    "resident"
                    if memory["resident"]
                    else "total"
                    if memory["total"]
                    else "legacy"
                ),
                "memoryBytes": sum(selected.values()),
            }
    return result


def raw_pipewire_kind(raw: dict[str, object]) -> str:
    def source_kind(props: dict[str, object]) -> str:
        media_class = str(props.get("media.class", ""))
        text = " ".join(
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
        if any(value in text for value in ("screen", "screencast", "screen-cast")):
            return "screen"
        if media_class == "Video/Source" and (
            any(value in text for value in ("camera", "webcam", "v4l2"))
            or str(props.get("device.api", "")).lower() == "v4l2"
        ):
            return "camera"
        if media_class == "Video/Source":
            return "video"
        if media_class == "Audio/Source" and not any(
            value in text for value in ("monitor", "virtual")
        ):
            return "microphone"
        return "audio" if media_class.startswith("Audio/") else "other"

    props = raw["props"]
    media_class = str(props.get("media.class", ""))
    text = " ".join(
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
    source_kinds = {source_kind(source) for source in raw.get("linkedSources", [])}
    if media_class == "Stream/Input/Audio":
        return "microphone" if "microphone" in source_kinds else "audio-capture"
    if media_class == "Stream/Input/Video":
        if "screen" in source_kinds or any(
            value in text for value in ("screen", "screencast", "screen-cast")
        ):
            return "screen"
        if "camera" in source_kinds or any(
            value in text for value in ("camera", "webcam")
        ):
            return "camera"
        return "video"
    if media_class == "Stream/Output/Audio":
        return "audio"
    if media_class == "Stream/Output/Video":
        return "video"
    return "other"


def raw_pipewire_streams() -> dict[tuple[int, int], dict[str, object]]:
    if not shutil.which("pw-dump"):
        return {}
    payload = command_json(["pw-dump"])
    if not isinstance(payload, list):
        return {}
    clients: dict[int, dict[str, object]] = {}
    nodes: dict[int, dict[str, object]] = {}
    links: list[tuple[int, int]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        props = info.get("props") if isinstance(info.get("props"), dict) else {}
        if str(item.get("type", "")).endswith(":Client"):
            clients[int(item.get("id", 0))] = props
        elif str(item.get("type", "")).endswith(":Node"):
            nodes[int(item.get("id", 0))] = props
        elif str(item.get("type", "")).endswith(":Link") and str(
            info.get("state", "")
        ).lower() in {"active", "running"}:
            try:
                links.append(
                    (
                        int(props.get("link.output.node", 0)),
                        int(props.get("link.input.node", 0)),
                    )
                )
            except (TypeError, ValueError):
                continue
    adjacency: dict[int, set[int]] = {}
    for output_node, input_node in links:
        if output_node <= 0 or input_node <= 0:
            continue
        adjacency.setdefault(output_node, set()).add(input_node)
        adjacency.setdefault(input_node, set()).add(output_node)

    components: dict[int, tuple[int, ...]] = {}

    def linked_nodes(start: int) -> list[int]:
        if start in components:
            return [node for node in components[start] if node != start]
        pending = deque([start])
        seen: set[int] = set()
        while pending:
            current = pending.popleft()
            if current in seen:
                continue
            seen.add(current)
            pending.extend(adjacency.get(current, set()) - seen)
        component = tuple(sorted(seen))
        for node in component:
            components[node] = component
        return [node for node in component if node != start]

    rows: dict[tuple[int, int], dict[str, object]] = {}
    for item in payload:
        if not isinstance(item, dict) or not str(item.get("type", "")).endswith(
            ":Node"
        ):
            continue
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        props = info.get("props") if isinstance(info.get("props"), dict) else {}
        if not str(props.get("media.class", "")).startswith("Stream/"):
            continue
        owner = clients.get(int(props.get("client.id", 0) or 0), {})
        pid = int(
            props.get("application.process.id")
            or owner.get("application.process.id")
            or 0
        )
        identity = int(props.get("object.serial") or item.get("id") or 0)
        node_id = int(item.get("id") or 0)
        linked = linked_nodes(node_id)
        linked_sources = [nodes[node] for node in linked if node in nodes]
        if pid > 0 and identity > 0:
            rows[(identity, pid)] = {
                "info": info,
                "props": props,
                "mediaClass": str(props.get("media.class", "")),
                "role": str(props.get("media.role", props.get("node.role", ""))),
                "name": str(
                    props.get(
                        "media.name",
                        props.get("node.description", props.get("node.name", "")),
                    )
                    or props.get("media.class", "")
                    or f"PipeWire node {node_id}"
                ),
                "application": str(
                    props.get("application.name")
                    or props.get("application.process.binary")
                    or owner.get("application.name")
                    or owner.get("application.process.binary", "")
                ),
                "state": str(info.get("state", "unknown")).title(),
                "active": str(info.get("state", "")).lower() in {"active", "running"},
                "sourceIds": sorted(
                    node
                    for node in linked
                    if node in nodes
                    and str(nodes[node].get("media.class", "")).endswith("/Source")
                ),
                "linkedSources": linked_sources,
                "source": next(
                    (
                        str(source.get("node.description") or source.get("node.name"))
                        for source in linked_sources
                        if source.get("node.description") or source.get("node.name")
                    ),
                    "",
                ),
            }
    return rows


def rendered_details(snapshot: dict[str, object]) -> dict[str, object]:
    if not QML:
        raise AssertionError("qml6 or qml is required for the drilldown oracle")
    payload = {
        key: snapshot[key]
        for key in (
            "target",
            "metrics",
            "processes",
            "connections",
            "files",
            "locks",
            "devices",
            "context",
            "security",
            "logs",
            "explanations",
            "timeline",
            "coverage",
            "samplingPaused",
        )
    }
    serialized = json.dumps(payload, separators=(",", ":"))
    chunks = [
        serialized[index : index + 32_000]
        for index in range(0, len(serialized), 32_000)
    ]
    completed = subprocess.run(
        [QML, "-platform", "offscreen", str(DETAIL_ORACLE), "--", *chunks],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
        env={
            **os.environ,
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_TO_CONSOLE": "1",
        },
    )
    output = completed.stdout + "\n" + completed.stderr
    if completed.returncode != 0:
        raise AssertionError(output)
    return parse_json_marker(output, "XRAY_LIVE_DETAILS")
