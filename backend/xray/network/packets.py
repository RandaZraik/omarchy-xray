from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
import struct


def normalized_address(value: str) -> str:
    address = ipaddress.ip_address(value)
    return str(
        address.ipv4_mapped
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped
        else address
    )


@dataclass(frozen=True)
class PacketKey:
    protocol: str
    source: str
    source_port: int
    destination: str
    destination_port: int

    def reverse(self) -> PacketKey:
        return PacketKey(
            self.protocol,
            self.destination,
            self.destination_port,
            self.source,
            self.source_port,
        )


@dataclass(frozen=True)
class Packet:
    key: PacketKey
    ip_bytes: int
    transport_bytes: int
    link_bytes: int


def parse_packet(data: bytes, link_type: int = 101) -> Packet | None:
    """Decode headers only; byte counts use IP lengths, never captured payload size."""
    offset = 0
    if link_type == 1:  # Ethernet, including VLAN tags
        if len(data) < 14:
            return None
        protocol = struct.unpack_from("!H", data, 12)[0]
        offset = 14
        for _ in range(2):
            if protocol not in (0x8100, 0x88A8):
                break
            if len(data) < offset + 4:
                return None
            protocol = struct.unpack_from("!H", data, offset + 2)[0]
            offset += 4
        if protocol not in (0x0800, 0x86DD):
            return None
    elif link_type == 113:  # Linux cooked v1
        if len(data) < 16 or struct.unpack_from("!H", data, 14)[0] not in (
            0x0800,
            0x86DD,
        ):
            return None
        offset = 16
    elif link_type == 276:  # Linux cooked v2
        if len(data) < 20 or struct.unpack_from("!H", data)[0] not in (0x0800, 0x86DD):
            return None
        offset = 20
    elif link_type not in (101, 228, 229):
        return None
    link_bytes = offset
    if len(data) <= offset:
        return None
    version = data[offset] >> 4
    if version == 4:
        if len(data) < offset + 20:
            return None
        header_size = (data[offset] & 15) * 4
        ip_bytes = struct.unpack_from("!H", data, offset + 2)[0]
        # No fragment can safely be assigned without bounded reassembly.
        if header_size < 20 or struct.unpack_from("!H", data, offset + 6)[0] & 0x3FFF:
            return None
        protocol = data[offset + 9]
        source = socket.inet_ntop(socket.AF_INET, data[offset + 12 : offset + 16])
        destination = socket.inet_ntop(socket.AF_INET, data[offset + 16 : offset + 20])
        offset += header_size
    elif version == 6:
        if len(data) < offset + 40:
            return None
        payload_size = struct.unpack_from("!H", data, offset + 4)[0]
        if not payload_size:  # Jumbo payloads need a separate option parser.
            return None
        ip_bytes = payload_size + 40
        protocol = data[offset + 6]
        source = normalized_address(
            socket.inet_ntop(socket.AF_INET6, data[offset + 8 : offset + 24])
        )
        destination = normalized_address(
            socket.inet_ntop(socket.AF_INET6, data[offset + 24 : offset + 40])
        )
        offset += 40
        for _ in range(8):
            if protocol not in (0, 43, 60, 51, 44):
                break
            if len(data) < offset + 8:
                return None
            if protocol == 44:
                if struct.unpack_from("!H", data, offset + 2)[0] & 0xFFF9:
                    return None
                size = 8
            else:
                size = (data[offset + 1] + (2 if protocol == 51 else 1)) * (
                    4 if protocol == 51 else 8
                )
            protocol = data[offset]
            offset += size
    else:
        return None
    transport_bytes = ip_bytes - (offset - link_bytes)
    minimum = 20 if protocol == 6 else 8 if protocol == 17 else 0
    if not minimum or transport_bytes < minimum or len(data) < offset + minimum:
        return None
    if protocol == 6:
        tcp_header = (data[offset + 12] >> 4) * 4
        if (
            tcp_header < 20
            or tcp_header > transport_bytes
            or len(data) < offset + tcp_header
        ):
            return None
    else:
        udp_length = struct.unpack_from("!H", data, offset + 4)[0]
        if udp_length < 8 or udp_length > transport_bytes:
            return None
    source_port, destination_port = struct.unpack_from("!HH", data, offset)
    return Packet(
        PacketKey(
            "TCP" if protocol == 6 else "UDP",
            source,
            source_port,
            destination,
            destination_port,
        ),
        ip_bytes,
        transport_bytes,
        link_bytes,
    )


class PcapStream:
    """Incremental classic-PCAP decoder for dumpcap's bounded header stream."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.endian = ""
        self.link_type = 0

    def feed(self, chunk: bytes) -> list[Packet | None]:
        self.buffer.extend(chunk)
        result: list[Packet | None] = []
        if not self.endian:
            if len(self.buffer) < 24:
                return result
            magic = bytes(self.buffer[:4])
            self.endian = {
                b"\xd4\xc3\xb2\xa1": "<",
                b"\xa1\xb2\xc3\xd4": ">",
                b"\x4d\x3c\xb2\xa1": "<",
                b"\xa1\xb2\x3c\x4d": ">",
            }.get(magic, "")
            if not self.endian:
                raise ValueError("Packet capture returned an unsupported stream")
            self.link_type = (
                struct.unpack_from(self.endian + "I", self.buffer, 20)[0] & 0xFFFF
            )
            if self.link_type not in (1, 101, 113, 228, 229, 276):
                raise ValueError("Packet capture returned an unsupported link type")
            del self.buffer[:24]
        while len(self.buffer) >= 16:
            size = struct.unpack_from(self.endian + "I", self.buffer, 8)[0]
            if size > 65536:
                raise ValueError("Packet capture exceeded the packet size limit")
            if len(self.buffer) < 16 + size:
                break
            result.append(
                parse_packet(bytes(self.buffer[16 : 16 + size]), self.link_type)
            )
            del self.buffer[: 16 + size]
        return result
