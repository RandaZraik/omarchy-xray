from __future__ import annotations

from dataclasses import dataclass
import socket
import struct
import time

from xray.config import LIMITS, TIMING


@dataclass(frozen=True)
class TcpCounter:
    inode: int
    cookie: str
    local_address: str
    local_port: int
    remote_address: str
    remote_port: int
    sent: int
    received: int
    rtt_ms: float
    retransmits: int


def parse_diagnostic(payload: bytes) -> TcpCounter | None:
    # Linux UAPI: inet_diag_msg (72 bytes), followed by aligned rtattrs.
    if len(payload) < 72 or payload[0] not in (socket.AF_INET, socket.AF_INET6):
        return None
    family = payload[0]
    size = 4 if family == socket.AF_INET else 16
    local_port, remote_port = struct.unpack_from("!HH", payload, 4)
    inode = struct.unpack_from("=I", payload, 68)[0]
    if not inode:
        return None
    offset = 72
    while offset + 4 <= len(payload):
        length, kind = struct.unpack_from("=HH", payload, offset)
        if length < 4 or offset + length > len(payload):
            break
        info = payload[offset + 4 : offset + length]
        if kind == 2 and len(info) >= 136:  # INET_DIAG_INFO / tcp_info
            sent, received = struct.unpack_from("=QQ", info, 120)
            return TcpCounter(
                inode=inode,
                cookie=payload[44:52].hex(),
                local_address=socket.inet_ntop(family, payload[8 : 8 + size]),
                local_port=local_port,
                remote_address=socket.inet_ntop(family, payload[24 : 24 + size]),
                remote_port=remote_port,
                sent=sent,
                received=received,
                rtt_ms=struct.unpack_from("=I", info, 68)[0] / 1000,
                retransmits=struct.unpack_from("=I", info, 100)[0],
            )
        offset += (length + 3) & ~3
    return None


def tcp_counters(
    families: tuple[int, ...] = (socket.AF_INET, socket.AF_INET6),
) -> tuple[dict[int, TcpCounter], list[str]]:
    """Read TCP_INFO through SOCK_DIAG in the caller's network namespace."""
    counters: dict[int, TcpCounter] = {}
    limited: list[str] = []
    deadline = time.monotonic() + TIMING.network_diag_seconds
    try:
        with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 4) as netlink:
            netlink.bind((0, 0))
            consumed = 0
            for sequence, family in enumerate(families, 1):
                request = struct.pack("=BBBBI", family, socket.IPPROTO_TCP, 2, 0, 0xFFF)
                request += bytes(40) + b"\xff" * 8
                header = struct.pack(
                    "=IHHII", 16 + len(request), 20, 0x301, sequence, 0
                )
                netlink.send(header + request)
                done = False
                while not done:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("TCP counter collection timed out")
                    netlink.settimeout(remaining)
                    data, _ancillary, flags, _address = netlink.recvmsg(65536)
                    consumed += len(data)
                    if flags & socket.MSG_TRUNC or consumed > LIMITS.network_diag_bytes:
                        raise OSError("TCP counter collection exceeded its read limit")
                    offset = 0
                    while offset + 16 <= len(data):
                        length, kind, message_flags, seq, _pid = struct.unpack_from(
                            "=IHHII", data, offset
                        )
                        if length < 16 or offset + length > len(data):
                            raise OSError("Incomplete TCP counter response")
                        payload = data[offset + 16 : offset + length]
                        offset += (length + 3) & ~3
                        if seq != sequence:
                            continue
                        if message_flags & 0x10:
                            limited.append(
                                "TCP sockets changed during counter collection"
                            )
                        if kind == 3:
                            done = True
                            break
                        if kind == 2:
                            error = (
                                struct.unpack_from("=i", payload)[0]
                                if len(payload) >= 4
                                else -1
                            )
                            if error:
                                raise OSError(
                                    abs(error), "TCP counters are unavailable"
                                )
                        elif kind == 20:
                            counter = parse_diagnostic(payload)
                            if counter:
                                counters[counter.inode] = counter
    except OSError as error:
        limited.append(str(error) or "TCP counters are unavailable")
    return counters, limited
