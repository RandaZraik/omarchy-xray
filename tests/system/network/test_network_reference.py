"""Opt-in comparisons against pinned upstream source (see support.network_reference).

Build the harness once, then set XRAY_NETWORK_REFERENCE to its executable.
Raw capture tests run inside `unshare --user --map-root-user --net` with lo up;
this grants capture rights only in a disposable network namespace.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import select
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from support.live_backend import wait_until

from support.network import packet_bytes
from support.network_live import TcpFixture
from support.network_reference import REVISIONS, compare
from xray.network.packets import parse_packet
from xray.network.sockets import collect_connections
from xray.network.traffic import NetworkMonitor
from xray.processes.identity import identity_for
from xray.system.commands import CommandRunner
from xray.system.procfs import ProcFs


REFERENCE = Path(os.environ.get("XRAY_NETWORK_REFERENCE", "/missing"))


def start_capture(monitor):
    executable = os.environ.get("XRAY_NETWORK_DUMPCAP")
    if executable:
        # Select the fallback; packets still come from the real dumpcap binary.
        with (
            patch("xray.network.capture.socket.socket", side_effect=PermissionError),
            patch("xray.network.capture.shutil.which", return_value=executable),
        ):
            monitor.configure(capture=True, interface="lo")
        assert wait_until(lambda: not monitor.capture.starting), (
            monitor.capture.status()
        )
        assert monitor.capture.source == "dumpcap"
    else:
        monitor.configure(capture=True, interface="lo")
    assert monitor.capture.active, monitor.capture.error


def settle_capture(capture):
    # libpcap batches delivery; wait for a quiet batch instead of assuming the
    # raw socket's immediate delivery timing for the dumpcap fallback.
    previous = 0
    changed_at = time.monotonic()

    def settled():
        nonlocal previous, changed_at
        with capture._lock:
            count = sum(value[1] for value in capture._counts.values())
        if count != previous:
            previous, changed_at = count, time.monotonic()
        return count > 0 and time.monotonic() - changed_at >= 0.2

    assert wait_until(settled, timeout=3), capture.status()


@contextmanager
def observed_packets():
    """Independent full-packet receiver; the reference code does all decoding."""
    captured = []
    stopped = threading.Event()
    with socket.socket(socket.AF_PACKET, socket.SOCK_DGRAM, socket.htons(3)) as reader:
        reader.bind(("lo", 0))
        reader.settimeout(0.1)

        def read():
            while not stopped.is_set():
                try:
                    data, address = reader.recvfrom(65536)
                except TimeoutError:
                    continue
                if address[2] != 4:
                    captured.append(data)

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        try:
            yield captured
        finally:
            stopped.set()
            thread.join(timeout=1)


@unittest.skipUnless(
    REFERENCE.is_file(), "set XRAY_NETWORK_REFERENCE to the built upstream harness"
)
class UpstreamNetworkTests(unittest.TestCase):
    def test_identical_frames_match_both_upstream_parsers_and_bandwhich_totals(self):
        frames = []
        for protocol in ("TCP", "UDP"):
            for ipv6 in (False, True):
                for payload in (0, 1, 100, 1400, 32000):
                    for upload in (False, True):
                        local = "2001:db8::1" if ipv6 else "10.0.0.2"
                        remote = "2001:4860::8888" if ipv6 else "1.1.1.1"
                        data = packet_bytes(
                            protocol,
                            payload,
                            ipv6,
                            source=local if upload else remote,
                            destination=remote if upload else local,
                            source_port=41000 if upload else 443,
                            destination_port=443 if upload else 41000,
                            ethernet=True,
                        )
                        frames.append({"hex": data.hex(), "local": [local], "link": 1})
        reference = compare(REFERENCE, frames)
        totals = {"sent": 0, "received": 0}
        for fixture, expected in zip(frames, reference["frames"]):
            packet = parse_packet(bytes.fromhex(fixture["hex"]), fixture["link"])
            bandwhich, sniffnet = expected["bandwhich"], expected["sniffnet"]
            self.assertIsNotNone(packet)
            self.assertIsNotNone(bandwhich)
            self.assertIsNotNone(sniffnet)
            self.assertEqual(packet.transport_bytes, bandwhich["bytes"])
            self.assertEqual(packet.ip_bytes + packet.link_bytes, sniffnet["bytes"])
            self.assertEqual(packet.key.source, sniffnet["source"])
            self.assertEqual(packet.key.destination, sniffnet["destination"])
            self.assertEqual(packet.key.source_port, sniffnet["sourcePort"])
            self.assertEqual(packet.key.destination_port, sniffnet["destinationPort"])
            upload = packet.key.source in fixture["local"]
            self.assertEqual(bandwhich["direction"], "Upload" if upload else "Download")
            self.assertEqual(bandwhich["localPort"], 41000)
            self.assertEqual(bandwhich["remotePort"], 443)
            totals["sent" if upload else "received"] += packet.transport_bytes
        for direction in totals:
            self.assertEqual(
                totals[direction],
                sum(row[direction] for row in reference["bandwhichTotals"]),
            )
        print(
            "XRAY_NETWORK_REFERENCE "
            + json.dumps(
                {
                    "revisions": REVISIONS,
                    "comparedFrames": len(frames),
                    "bandwhichTransportBytes": totals,
                    "sniffnetFrameBytes": sum(
                        row["sniffnet"]["bytes"] for row in reference["frames"]
                    ),
                }
            )
        )

    def test_live_process_socket_ownership_matches_both_references(self):
        for ipv6 in (False, True):
            with (
                self.subTest(ipv6=ipv6),
                TcpFixture(ipv6) as first,
                TcpFixture(ipv6) as second,
            ):
                reference = compare(
                    REFERENCE, [], [first.local_port, second.local_port]
                )
                rows, limited = collect_connections(
                    ProcFs(), [first.process.pid, second.process.pid]
                )
                self.assertFalse(limited)
                for fixture in (first, second):
                    actual = next(
                        row for row in rows if row["localPort"] == fixture.local_port
                    )
                    expected = next(
                        row
                        for row in reference["owners"]
                        if row["port"] == fixture.local_port
                    )
                    self.assertEqual(actual["pids"], [expected["pid"]])
                    self.assertEqual(expected["pid"], fixture.process.pid)
                    self.assertEqual(actual["localAddress"], expected["address"])
                    sniffnet = next(
                        row
                        for row in reference["sniffnetOwners"]
                        if row["port"] == fixture.local_port
                    )
                    self.assertEqual(actual["pids"], [sniffnet["pid"]])

    @unittest.skipUnless(
        os.environ.get("XRAY_NETWORK_ISOLATED") == "1",
        "requires isolated capture namespace",
    )
    def test_live_packet_capture_tcp_v4_v6_matches_both_references(self):
        for ipv6 in (False, True):
            with self.subTest(ipv6=ipv6), TcpFixture(ipv6) as fixture:
                proc = ProcFs()
                monitor = NetworkMonitor(proc, CommandRunner())
                identity = identity_for(proc, fixture.process.pid)
                processes = [
                    {
                        "pid": identity.pid,
                        "startTime": identity.start_time,
                        "uid": identity.uid,
                        "name": "fixture",
                    }
                ]
                rows, limited = collect_connections(proc, [fixture.process.pid])
                try:
                    start_capture(monitor)
                    self.assertTrue(monitor.capture.active, monitor.capture.error)
                    monitor.sample(rows, processes, tuple(limited), 300)
                    with observed_packets() as frames:
                        fixture.transfer("send", 16384)
                        fixture.transfer("receive", 8192)
                        settle_capture(monitor.capture)
                        measured = monitor.sample(rows, processes, tuple(limited), 300)
                    reference = compare(
                        REFERENCE,
                        [
                            {
                                "hex": data.hex(),
                                "link": 101,
                                "local": ["::1" if ipv6 else "127.0.0.1"],
                            }
                            for data in frames
                        ],
                    )
                    expected_sent = expected_received = 0
                    for data, evidence in zip(frames, reference["frames"]):
                        packet = parse_packet(data)
                        if packet is None:
                            continue
                        self.assertEqual(
                            packet.transport_bytes, evidence["bandwhich"]["bytes"]
                        )
                        self.assertEqual(packet.ip_bytes, evidence["sniffnet"]["bytes"])
                        if packet.key.source_port == fixture.local_port:
                            expected_sent += packet.ip_bytes
                        elif packet.key.destination_port == fixture.local_port:
                            expected_received += packet.ip_bytes
                    self.assertGreater(expected_sent, 16384)
                    self.assertGreater(expected_received, 8192)
                    self.assertEqual(measured["totals"]["sentBytes"], expected_sent)
                    self.assertEqual(
                        measured["totals"]["receivedBytes"], expected_received
                    )
                    self.assertEqual(
                        measured["capture"]["droppedPackets"],
                        None if os.environ.get("XRAY_NETWORK_DUMPCAP") else 0,
                    )
                    print(
                        "XRAY_NETWORK_LIVE_PACKETS "
                        + json.dumps(
                            {
                                "ipv6": ipv6,
                                "frames": len(frames),
                                "sentIpBytes": expected_sent,
                                "receivedIpBytes": expected_received,
                            }
                        )
                    )
                finally:
                    monitor.close()

    @unittest.skipUnless(
        os.environ.get("XRAY_NETWORK_ISOLATED") == "1",
        "requires isolated capture namespace",
    )
    def test_live_udp_capture_counts_exact_datagrams_without_loopback_duplicates(self):
        for family, address in (
            (socket.AF_INET, "127.0.0.1"),
            (socket.AF_INET6, "::1"),
        ):
            with (
                self.subTest(family=family),
                socket.socket(family, socket.SOCK_DGRAM) as client,
                socket.socket(family, socket.SOCK_DGRAM) as peer,
            ):
                client.bind((address, 0))
                peer.bind((address, 0))
                client.settimeout(3)
                peer.settimeout(3)
                proc = ProcFs()
                identity = identity_for(proc, os.getpid())
                processes = [
                    {
                        "pid": identity.pid,
                        "startTime": identity.start_time,
                        "uid": identity.uid,
                        "name": "udp-fixture",
                    }
                ]
                rows, limited = collect_connections(proc, [identity.pid])
                # Monitor only the client FD so totals represent one endpoint.
                rows = [
                    row for row in rows if row["localPort"] == client.getsockname()[1]
                ]
                monitor = NetworkMonitor(proc, CommandRunner())
                try:
                    start_capture(monitor)
                    self.assertTrue(monitor.capture.active)
                    monitor.sample(rows, processes, tuple(limited), 300)
                    with observed_packets() as frames:
                        for _ in range(5):
                            client.sendto(b"x" * 512, peer.getsockname())
                            data, sender = peer.recvfrom(1024)
                            self.assertEqual(len(data), 512)
                            peer.sendto(b"x" * 256, sender)
                            self.assertEqual(len(client.recv(1024)), 256)
                        settle_capture(monitor.capture)
                        measured = monitor.sample(rows, processes, tuple(limited), 300)
                    ip_header = 20 if family == socket.AF_INET else 40
                    self.assertEqual(
                        measured["totals"]["sentBytes"], 5 * (512 + 8 + ip_header)
                    )
                    self.assertEqual(
                        measured["totals"]["receivedBytes"], 5 * (256 + 8 + ip_header)
                    )
                    flow = next(
                        row
                        for row in measured["flows"]
                        if row["remotePort"] == peer.getsockname()[1]
                    )
                    self.assertEqual(flow["sentPackets"], 5)
                    self.assertEqual(flow["receivedPackets"], 5)
                    reference = compare(
                        REFERENCE,
                        [
                            {"hex": data.hex(), "link": 101, "local": [address]}
                            for data in frames
                        ],
                    )
                    self.assertEqual(len(reference["frames"]), 10)
                    for data, result in zip(frames, reference["frames"]):
                        parsed = parse_packet(data)
                        self.assertEqual(
                            parsed.transport_bytes, result["bandwhich"]["bytes"]
                        )
                        self.assertEqual(parsed.ip_bytes, result["sniffnet"]["bytes"])
                finally:
                    monitor.close()

    @unittest.skipUnless(
        os.environ.get("XRAY_NETWORK_ISOLATED") == "1",
        "requires isolated capture namespace",
    )
    def test_real_unselected_reuseport_receiver_is_never_credited_to_selected_owner(
        self,
    ):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as selected:
            selected.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            selected.bind(("127.0.0.1", 0))
            port = selected.getsockname()[1]
            code = "import socket,sys; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEPORT,1); s.bind(('127.0.0.1',int(sys.argv[1]))); print('ready',flush=True); data=s.recv(1024); print(len(data),flush=True); sys.stdin.readline()"
            foreign = subprocess.Popen(
                [sys.executable, "-c", code, str(port)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            monitor = NetworkMonitor(ProcFs(), CommandRunner())
            try:
                self.assertEqual(foreign.stdout.readline().strip(), "ready")
                proc = ProcFs()
                rows, limited = collect_connections(proc, [os.getpid()])
                rows = [row for row in rows if row["localPort"] == port]
                self.assertEqual(len(rows), 1)
                self.assertTrue(rows[0]["packetAttributionLimited"])
                identity = identity_for(proc, os.getpid())
                processes = [
                    {
                        "pid": identity.pid,
                        "startTime": identity.start_time,
                        "uid": identity.uid,
                        "name": "selected",
                    }
                ]
                start_capture(monitor)
                self.assertTrue(monitor.capture.active)
                monitor.sample(rows, processes, tuple(limited), 300)
                for _ in range(100):
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                        sender.sendto(b"test", ("127.0.0.1", port))
                    if select.select([foreign.stdout], [], [], 0.02)[0]:
                        break
                self.assertTrue(
                    select.select([foreign.stdout], [], [], 1)[0],
                    "foreign fixture did not receive packet",
                )
                self.assertEqual(foreign.stdout.readline().strip(), "4")
                settle_capture(monitor.capture)
                result = monitor.sample(rows, processes, tuple(limited), 300)
                self.assertEqual(result["totals"]["receivedBytes"], 0)
                self.assertGreater(result["unattributedPackets"], 0)
                self.assertTrue(
                    any("share a port" in message for message in result["limited"])
                )
            finally:
                monitor.close()
                foreign.terminate()
                foreign.wait(timeout=3)
                for pipe in (foreign.stdin, foreign.stdout, foreign.stderr):
                    pipe.close()
