from __future__ import annotations

from contextlib import suppress
from functools import lru_cache
import os
from pathlib import Path
import selectors
import shutil
import socket
import struct
import subprocess
import threading
import time

from xray.config import LIMITS, TIMING
from xray.network.packets import Packet, PacketKey, PcapStream, parse_packet
from xray.system.procfs import ProcFs


def interfaces() -> list[str]:
    try:
        return [name for _index, name in socket.if_nameindex()]
    except OSError:
        return []


def interface_labels() -> dict[str, str]:
    try:
        available = socket.if_nameindex()
    except OSError:
        return {}
    return {
        name: _interface_label(index, name)
        if position < LIMITS.network_interface_labels else name
        for position, (index, name) in enumerate(available)
    }


@lru_cache(maxsize=LIMITS.network_interface_labels)
def _interface_label(index: int, name: str, root: Path = Path("/sys/class/net")) -> str:
    # The index distinguishes a replacement interface with the same name.
    sysfs = ProcFs(root)
    kind = sysfs.read(name, "type", limit=32).value.strip()
    if kind == "772":
        description = "This machine"
    elif sysfs.path(name, "wireless").is_dir():
        description = "Wi-Fi"
    elif sysfs.path(name, "bridge").is_dir():
        description = "Docker network" if name == "docker0" else "Network bridge"
    elif kind == "1" and sysfs.path(name, "device").exists():
        description = "Ethernet"
    elif sysfs.path(name, "tun_flags").is_file():
        description = "Tunnel"
    else:
        return name
    return f"{name} · {description}"


class PacketCapture:
    """Optional header-only capture, using permissions already granted externally."""

    def __init__(self) -> None:
        self.interface = ""
        self.source = ""
        self.error = ""
        self.error_kind = ""
        self.active = False
        self.starting = False
        self.dropped: int | None = 0
        self.skipped = 0
        self.overflow = 0
        self._counts: dict[PacketKey, list[int]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._process: subprocess.Popen[bytes] | None = None

    def start(self, interface: str) -> None:
        self.close()
        if interface not in interfaces():
            raise ValueError("Choose an available network interface")
        self.interface = interface
        self.error = ""
        self.error_kind = ""
        self.dropped = self.skipped = self.overflow = 0
        self._counts = {}
        self._stop.clear()
        try:
            capture = socket.socket(
                socket.AF_PACKET, socket.SOCK_DGRAM, socket.htons(3)
            )
            self._socket = capture
            capture.bind((interface, 0))
            capture.setsockopt(
                socket.SOL_SOCKET, socket.SO_RCVBUF, LIMITS.network_capture_buffer
            )
            capture.settimeout(0.2)
            self.source = "packet socket"
            self.active = True
            target = self._read_socket
        except OSError:
            if self._socket:
                self._socket.close()
                self._socket = None
            executable = shutil.which("dumpcap")
            if not executable:
                self.error = "Packet capture needs an installed dumpcap with capture permission. TCP payload measurements remain available."
                self.error_kind = "missing-helper"
                return
            try:
                self._process = subprocess.Popen(
                    [
                        executable,
                        "-q",
                        "-p",
                        "-i",
                        interface,
                        "-s",
                        "512",
                        "-P",
                        "-w",
                        "-",
                        "-f",
                        "tcp or udp",
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except OSError as error:
                self.error = str(error)
                self.error_kind = "helper-launch"
                return
            self.source = "dumpcap"
            self.starting = True
            self.dropped = None
            target = self._read_dumpcap
        self._thread = threading.Thread(
            target=target, name="xray-network-capture", daemon=True
        )
        self._thread.start()

    def _ingest(self, packet: Packet | None) -> None:
        with self._lock:
            if packet is None:
                self.skipped += 1
                return
            if (
                packet.key not in self._counts
                and len(self._counts) >= LIMITS.network_packet_flows
            ):
                self.overflow += 1
                return
            counts = self._counts.setdefault(packet.key, [0, 0])
            counts[0] += packet.ip_bytes
            counts[1] += 1

    def _read_socket(self) -> None:
        capture = self._socket
        try:
            while not self._stop.is_set() and capture:
                try:
                    data, address = capture.recvfrom(512)
                except TimeoutError:
                    continue
                # Linux loopback delivers an outgoing and an incoming copy.
                if self.interface == "lo" and address[2] == 4:
                    continue
                self._ingest(parse_packet(data))
        except OSError as error:
            if not self._stop.is_set():
                self.error = str(error)
        finally:
            self.active = False

    def _read_dumpcap(self) -> None:
        process = self._process
        if process is None:
            return
        stream = PcapStream()
        errors = bytearray()
        deadline = time.monotonic() + TIMING.network_capture_start_seconds
        try:
            with selectors.DefaultSelector() as selector:
                for pipe in (process.stdout, process.stderr):
                    if pipe:
                        os.set_blocking(pipe.fileno(), False)
                        selector.register(pipe, selectors.EVENT_READ)
                while not self._stop.is_set() and selector.get_map():
                    if self.starting and time.monotonic() >= deadline:
                        raise ValueError("Packet capture did not start in time")
                    for key, _events in selector.select(0.2):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        elif key.fileobj is process.stdout:
                            for packet in stream.feed(chunk):
                                self._ingest(packet)
                            if stream.endian:
                                self.active = True
                                self.starting = False
                        elif len(errors) < 2048:
                            errors.extend(chunk[: 2048 - len(errors)])
                if not self._stop.is_set():
                    self.error = (
                        errors.decode("utf-8", errors="replace").strip()
                        or "Packet capture ended"
                    )
        except (OSError, ValueError) as error:
            if not self._stop.is_set():
                self.error = str(error)
        finally:
            self.active = False
            self.starting = False
            self._stop_helper(process)

    @staticmethod
    def _stop_helper(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        with suppress(OSError):
            process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            with suppress(OSError):
                process.kill()
            process.wait(timeout=1)

    def drain(self) -> tuple[dict[PacketKey, list[int]], dict[str, object]]:
        with self._lock:
            counts, self._counts = self._counts, {}
            if self._socket:
                with suppress(OSError):
                    stats = self._socket.getsockopt(
                        263, 6, 8
                    )  # SOL_PACKET, PACKET_STATISTICS
                    self.dropped = (
                        int(self.dropped or 0) + struct.unpack("=II", stats)[1]
                    )
            return counts, self.status()

    def status(self) -> dict[str, object]:
        return {
            "active": self.active,
            "starting": self.starting,
            "interface": self.interface,
            "source": self.source,
            "error": self.error,
            "errorKind": self.error_kind,
            "droppedPackets": self.dropped,
            "skippedPackets": self.skipped,
            "overflowPackets": self.overflow,
        }

    def close(self) -> None:
        self._stop.set()
        if self._process:
            self._stop_helper(self._process)
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        if self._socket:
            self._socket.close()
            self._socket = None
        if self._process:
            for pipe in (self._process.stdout, self._process.stderr):
                if pipe:
                    pipe.close()
            self._process = None
        self.active = False
        self.starting = False
