from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess


QML = shutil.which("qml6") or shutil.which("qml")
DETAIL_ORACLE = Path(__file__).with_name("live_detail_oracle.qml")


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


def descriptor_mode(pid: int, fd: int) -> str | None:
    try:
        values = {
            key: value.strip()
            for line in Path(f"/proc/{pid}/fdinfo/{fd}").read_text().splitlines()
            if (key := line.partition(":")[0]) and (value := line.partition(":")[2])
        }
        access = int(values.get("flags", "0"), 8) & os.O_ACCMODE
    except (OSError, ValueError):
        return None
    return (
        "read/write"
        if access == os.O_RDWR
        else "write"
        if access == os.O_WRONLY
        else "read"
    )


def _decode_address(value: str, ipv6: bool) -> str:
    if ipv6:
        raw = bytes.fromhex(value)
        raw = b"".join(
            struct.pack(">I", struct.unpack("<I", raw[index : index + 4])[0])
            for index in range(0, 16, 4)
        )
        return socket.inet_ntop(socket.AF_INET6, raw)
    return socket.inet_ntop(socket.AF_INET, struct.pack("<I", int(value, 16)))


def raw_socket_inventory(pids: list[int]) -> dict[tuple[object, ...], set[int]]:
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
        for target in descriptor_targets(pid).values():
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


def raw_drm_clients(pids: list[int]) -> set[tuple[int, str, str]]:
    result: set[tuple[int, str, str]] = set()
    for pid in pids:
        for fd, target in descriptor_targets(pid).items():
            if not target.startswith("/dev/dri/"):
                continue
            try:
                lines = Path(f"/proc/{pid}/fdinfo/{fd}").read_text().splitlines()
            except OSError:
                continue
            client = next(
                (
                    line.partition(":")[2].strip()
                    for line in lines
                    if line.startswith("drm-client-id:")
                ),
                "",
            )
            if client:
                result.add((pid, target, client))
    return result


def raw_pipewire_streams() -> dict[tuple[int, int], dict[str, object]]:
    if not shutil.which("pw-dump"):
        return {}
    payload = command_json(["pw-dump"])
    if not isinstance(payload, list):
        return {}
    clients: dict[int, dict[str, object]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        props = info.get("props") if isinstance(info.get("props"), dict) else {}
        if str(item.get("type", "")).endswith(":Client"):
            clients[int(item.get("id", 0))] = props
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
        if pid > 0 and identity > 0:
            rows[(identity, pid)] = {"info": info, "props": props}
    return rows


def rendered_details(snapshot: dict[str, object]) -> dict[str, object]:
    if not QML:
        raise AssertionError("qml6 or qml is required for the drilldown oracle")
    payload = {
        key: snapshot[key]
        for key in (
            "target",
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
    marker = next(
        (
            line.partition("XRAY_LIVE_DETAILS ")[2]
            for line in output.splitlines()
            if "XRAY_LIVE_DETAILS " in line
        ),
        "",
    )
    if not marker:
        raise AssertionError(f"detail oracle returned no payload: {output}")
    return json.loads(marker)
