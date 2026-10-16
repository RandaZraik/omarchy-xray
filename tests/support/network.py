from __future__ import annotations

from dataclasses import replace
import socket
import struct

from xray.network.diagnostics import TcpCounter


NAMESPACE = "net:[123]"
PROCESS = {"pid": 42, "startTime": 100, "uid": 1000, "name": "client"}


def connection(**changes: object) -> dict[str, object]:
    return {
        "protocol": "TCP4",
        "localAddress": "10.0.0.2",
        "localPort": 41000,
        "remoteAddress": "1.1.1.1",
        "remotePort": 443,
        "inode": 7,
        "networkNamespace": NAMESPACE,
        "pids": [42],
        "state": "Established",
        "listening": False,
        "publicListener": False,
        "externallyReachable": False,
        **changes,
    }


def counter(sent: int, received: int, **changes: object) -> TcpCounter:
    return replace(
        TcpCounter(
            7, "cookie", "10.0.0.2", 41000, "1.1.1.1", 443, sent, received, 1.5, 0
        ),
        **changes,
    )


def packet_bytes(
    protocol: str = "TCP",
    payload: int = 100,
    ipv6: bool = False,
    source: str | None = None,
    destination: str | None = None,
    source_port: int = 41000,
    destination_port: int = 443,
    ethernet: bool = False,
    vlan: bool = False,
) -> bytes:
    if protocol == "TCP":
        transport = struct.pack(
            "!HHIIHHHH", source_port, destination_port, 1, 1, 0x5018, 65535, 0, 0
        )
    else:
        transport = struct.pack("!HHHH", source_port, destination_port, 8 + payload, 0)
    if ipv6:
        header = struct.pack(
            "!IHBB16s16s",
            6 << 28,
            len(transport) + payload,
            6 if protocol == "TCP" else 17,
            64,
            socket.inet_pton(socket.AF_INET6, source or "2001:db8::1"),
            socket.inet_pton(socket.AF_INET6, destination or "2001:4860::8888"),
        )
    else:
        header = struct.pack(
            "!BBHHHBBH4s4s",
            0x45,
            0,
            20 + len(transport) + payload,
            1,
            0,
            64,
            6 if protocol == "TCP" else 17,
            0,
            socket.inet_aton(source or "10.0.0.2"),
            socket.inet_aton(destination or "1.1.1.1"),
        )
    link = b""
    if ethernet:
        link = bytes(12) + struct.pack(
            "!H", 0x8100 if vlan else 0x86DD if ipv6 else 0x0800
        )
        if vlan:
            link += struct.pack("!HH", 5, 0x86DD if ipv6 else 0x0800)
    return link + header + transport + b"x" * payload
