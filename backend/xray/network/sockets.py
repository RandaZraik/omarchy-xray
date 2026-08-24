from __future__ import annotations

from collections import defaultdict
import ipaddress
import re
import socket
import struct

from xray.config import LIMITS
from xray.system.procfs import ProcFs
from xray.system.descriptors import DescriptorInventory, collect_descriptors
from xray.processes.identity import same_user_pids


_SOCKET_LINK = re.compile(r"^socket:\[(\d+)]$")
_TCP_STATES = {
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


def decode_address(value: str, ipv6: bool) -> str:
    if ipv6:
        raw = bytes.fromhex(value)
        if len(raw) != 16:
            raise ValueError("invalid IPv6 address")
        raw = b"".join(
            struct.pack(">I", struct.unpack("<I", raw[index : index + 4])[0])
            for index in range(0, 16, 4)
        )
        return socket.inet_ntop(socket.AF_INET6, raw)
    raw = struct.pack("<I", int(value, 16))
    return socket.inet_ntop(socket.AF_INET, raw)


def parse_endpoint(value: str, ipv6: bool) -> tuple[str, int]:
    address, separator, port = value.partition(":")
    if not separator:
        raise ValueError("invalid endpoint")
    return decode_address(address, ipv6), int(port, 16)


def parse_socket_table(text: str, protocol: str) -> list[dict[str, object]]:
    ipv6 = protocol.endswith("6")
    transport = "TCP" if protocol.startswith("tcp") else "UDP"
    rows: list[dict[str, object]] = []
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 10:
            continue
        try:
            local_address, local_port = parse_endpoint(fields[1], ipv6)
            remote_address, remote_port = parse_endpoint(fields[2], ipv6)
            inode = int(fields[9])
        except (ValueError, OSError):
            continue
        state_code = fields[3].upper()
        state = (
            _TCP_STATES.get(state_code, state_code) if transport == "TCP" else "Open"
        )
        listening = state_code == "0A" or (transport == "UDP" and remote_port == 0)
        try:
            local_ip = ipaddress.ip_address(local_address)
            beyond_loopback = not local_ip.is_loopback
        except ValueError:
            beyond_loopback = False
        rows.append(
            {
                "protocol": transport + ("6" if ipv6 else "4"),
                "localAddress": local_address,
                "localPort": local_port,
                "remoteAddress": remote_address,
                "remotePort": remote_port,
                "state": state,
                "inode": inode,
                "listening": listening,
                "publicListener": (local_address in {"0.0.0.0", "::"}) and listening,
                "externallyReachable": listening and beyond_loopback,
            }
        )
    return rows


def socket_owners(
    proc: ProcFs,
    pids: list[int],
    inventory: DescriptorInventory | None = None,
    namespaces: dict[int, str] | None = None,
) -> tuple[dict[tuple[str, int], list[int]], list[str]]:
    owners: dict[tuple[str, int], list[int]] = defaultdict(list)
    descriptors = inventory or collect_descriptors(proc, pids)
    limited = list(descriptors.limited)
    namespace_by_pid, namespace_limited = (
        (namespaces, []) if namespaces is not None else network_namespaces(proc, pids)
    )
    limited.extend(namespace_limited)
    selected = set(pids)
    for record in descriptors.records:
        if record.pid not in selected:
            continue
        match = _SOCKET_LINK.fullmatch(record.target)
        if match:
            inode = int(match.group(1))
            namespace = namespace_by_pid.get(record.pid, "")
            if not namespace:
                limited.append(
                    f"Network namespace is unavailable for process {record.pid}"
                )
                continue
            key = (namespace, inode)
            if record.pid not in owners[key]:
                owners[key].append(record.pid)
    return dict(owners), list(dict.fromkeys(limited))


def _network_namespace(proc: ProcFs, pid: int) -> str:
    result = proc.readlink(pid, "ns", "net")
    return result.value if result.available else ""


def network_namespaces(
    proc: ProcFs, pids: list[int]
) -> tuple[dict[int, str], list[str]]:
    namespaces: dict[int, str] = {}
    limited: list[str] = []
    for pid in pids:
        namespace = _network_namespace(proc, pid)
        if namespace:
            namespaces[pid] = namespace
        else:
            limited.append(f"Network namespace is unavailable for process {pid}")
    return namespaces, limited


def socket_rows(
    proc: ProcFs, root_pid: int | None = None, namespace: str = ""
) -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    limited: list[str] = []
    prefix: tuple[str | int, ...] = (root_pid, "net") if root_pid else ("net",)
    row_namespace = namespace or (
        _network_namespace(proc, root_pid) if root_pid else "default"
    )
    for table in ("tcp", "tcp6", "udp", "udp6"):
        content = proc.read(*prefix, table, limit=LIMITS.socket_table_bytes)
        if content.available:
            parsed = parse_socket_table(content.value, table)
            for row in parsed:
                row["networkNamespace"] = row_namespace
            rows.extend(parsed)
        elif content.error == "permission denied":
            limited.append(f"{table.upper()} table is permission-limited")
        else:
            limited.append(f"{table.upper()} table is unavailable")
    return rows, list(dict.fromkeys(limited))


def socket_rows_for_namespaces(
    proc: ProcFs,
    pids: list[int],
    namespaces: dict[int, str] | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    namespace_by_pid, limited = (
        (namespaces, []) if namespaces is not None else network_namespaces(proc, pids)
    )
    representatives: dict[str, int] = {}
    for pid, namespace in namespace_by_pid.items():
        representatives.setdefault(namespace, pid)
    if len(representatives) > LIMITS.network_namespaces:
        limited.append(
            f"Network sockets are limited to {LIMITS.network_namespaces} namespaces"
        )
        representatives = dict(
            list(representatives.items())[: LIMITS.network_namespaces]
        )
    rows: list[dict[str, object]] = []
    for namespace, pid in representatives.items():
        namespace_rows, namespace_limited = socket_rows(proc, pid, namespace)
        rows.extend(namespace_rows)
        limited.extend(namespace_limited)
    return rows, list(dict.fromkeys(limited))


def owned_socket_rows(
    proc: ProcFs,
    pids: list[int],
    inventory: DescriptorInventory | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    namespaces, limited = network_namespaces(proc, pids)
    owners, owner_limited = socket_owners(proc, pids, inventory, namespaces)
    rows, table_limited = socket_rows_for_namespaces(proc, pids, namespaces)
    limited.extend(owner_limited)
    limited.extend(table_limited)
    for row in rows:
        row["pids"] = owners.get((str(row["networkNamespace"]), int(row["inode"])), [])
    return rows, list(dict.fromkeys(limited))


def collect_connections(
    proc: ProcFs,
    pids: list[int],
    inventory: DescriptorInventory | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    socket_data, limited = owned_socket_rows(proc, pids, inventory)
    rows = [row for row in socket_data if row["pids"]]
    rows.sort(
        key=lambda row: (
            not bool(row["listening"]),
            int(row["localPort"]),
            str(row["protocol"]),
            int(row["inode"]),
        )
    )
    return rows, limited


def owners_for_port(
    proc: ProcFs,
    port: int,
    inventory: DescriptorInventory | None = None,
    pids: list[int] | None = None,
) -> tuple[list[int], list[str]]:
    all_pids = pids if pids is not None else same_user_pids(proc)
    rows, limited = owned_socket_rows(proc, all_pids, inventory)
    priority_by_pid: dict[int, int] = {}
    for row in rows:
        local_match = int(row["localPort"]) == port
        remote_match = int(row["remotePort"]) == port
        if not local_match and not remote_match:
            continue
        priority = 0 if local_match and row["listening"] else 1 if local_match else 2
        for pid in row["pids"]:
            normalized = int(pid)
            priority_by_pid[normalized] = min(
                priority, priority_by_pid.get(normalized, priority)
            )
    return sorted(priority_by_pid, key=lambda pid: (priority_by_pid[pid], pid)), limited
