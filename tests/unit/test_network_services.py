from dataclasses import replace
from pathlib import Path
import struct
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from support.live_backend import wait_until
from support.network import packet_bytes, connection, PROCESS, NAMESPACE
from xray.config import LIMITS, TIMING
from xray.network.capture import PacketCapture, _interface_label, interface_labels
from xray.network.names import DestinationNames
from xray.network.packets import parse_packet
from xray.network.traffic import NetworkMonitor
from xray.system.commands import CommandResult


def wait_for(predicate, timeout=3):
    if not wait_until(predicate, timeout):
        raise AssertionError("Network worker did not reach expected state")


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.capture = PacketCapture()
        self.addCleanup(self.capture.close)

    def helper(self, directory, code):
        helper = Path(directory) / "dumpcap"
        helper.write_text("#!/usr/bin/env python3\n" + code)
        helper.chmod(0o700)
        return str(helper)

    def start_helper(self, executable):
        with (
            patch("xray.network.capture.interfaces", return_value=["test0"]),
            patch("xray.network.capture.socket.socket", side_effect=PermissionError),
            patch("xray.network.capture.shutil.which", return_value=executable),
        ):
            self.capture.start("test0")

    def test_missing_capture_permission_preserves_fallback(self):
        self.start_helper(None)
        self.assertFalse(self.capture.active)
        self.assertFalse(self.capture.starting)
        self.assertIn("TCP payload measurements remain available", self.capture.error)
        self.assertEqual(self.capture.status()["errorKind"], "missing-helper")
        self.assertEqual(self.capture.drain()[0], {})

    def test_helper_stream_is_aggregated_and_stop_reaps_process(self):
        self.start_helper(None)
        frame = packet_bytes("UDP", 100, ethernet=True)
        pcap = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 512, 1)
        pcap += struct.pack("<IIII", 0, 0, len(frame), len(frame)) + frame
        with tempfile.TemporaryDirectory() as directory:
            helper = self.helper(
                directory,
                f"import sys, time\nsys.stdout.buffer.write({pcap!r})\nsys.stdout.buffer.flush()\ntime.sleep(60)\n",
            )
            self.start_helper(helper)
            process = self.capture._process
            thread = self.capture._thread
            wait_for(lambda: self.capture.active)
            counts, status = self.capture.drain()
            self.assertEqual(list(counts.values()), [[128, 1]])
            self.assertEqual(status["source"], "dumpcap")
            self.assertEqual(status["errorKind"], "")
            self.assertIsNone(status["droppedPackets"])
            self.capture.close()
            self.assertIsNotNone(process.poll())
            self.assertFalse(thread.is_alive())
            self.assertTrue(process.stdout.closed)
            self.assertTrue(process.stderr.closed)

    def test_helper_permission_error_malformed_stream_and_start_timeout(self):
        cases = [
            (
                "import sys\nsys.stderr.write('permission denied')\n",
                "permission denied",
            ),
            ("import sys\nsys.stdout.buffer.write(b'x' * 24)\n", "unsupported stream"),
            ("import time\ntime.sleep(60)\n", "did not start"),
        ]
        for code, expected in cases:
            with (
                self.subTest(expected=expected),
                tempfile.TemporaryDirectory() as directory,
                patch(
                    "xray.network.capture.TIMING",
                    replace(TIMING, network_capture_start_seconds=0.1),
                ),
            ):
                self.start_helper(self.helper(directory, code))
                process = self.capture._process
                wait_for(lambda: not self.capture.starting)
                self.assertIn(expected.lower(), self.capture.error.lower())
                self.assertFalse(self.capture.active)
                wait_for(lambda: process.poll() is not None)
                self.capture.close()

    def test_capture_budget_keeps_counts_bounded_and_reports_loss(self):
        with patch(
            "xray.network.capture.LIMITS", replace(LIMITS, network_packet_flows=2)
        ):
            for port in range(41000, 41004):
                self.capture._ingest(parse_packet(packet_bytes(source_port=port)))
            self.capture._ingest(None)
            counts, status = self.capture.drain()
            self.assertEqual(len(counts), 2)
            self.assertEqual(status["overflowPackets"], 2)
            self.assertEqual(status["skippedPackets"], 1)
            self.assertEqual(self.capture.drain()[0], {})

    def test_pause_resume_also_stops_a_starting_helper(self):
        monitor = NetworkMonitor(Mock(), Mock())
        monitor.capture = Mock(interface="test0", active=False, starting=True)
        monitor.pause(True)
        monitor.capture.close.assert_called_once()
        monitor.pause(False)
        monitor.capture.start.assert_called_once_with("test0")
        monitor.close()
        self.assertEqual(monitor._paused_interface, "")

    def test_resume_falls_back_to_tcp_if_the_capture_interface_disappears(self):
        proc = Mock(root=Path("/fixture-proc"))
        proc.readlink.return_value.value = NAMESPACE
        monitor = NetworkMonitor(proc, Mock())
        self.addCleanup(monitor.close)
        monitor.capture.interface = "removed0"
        monitor.capture.active = True
        monitor.pause(True)
        with patch("xray.network.capture.interfaces", return_value=[]):
            monitor.pause(False)
            monitor.pause(False)
        self.assertEqual(monitor._paused_interface, "")
        result = monitor.sample([], [], (), 300)
        self.assertEqual(result["mode"], "tcp")
        self.assertFalse(result["capture"]["active"])
        self.assertEqual(result["capture"]["errorKind"], "interface-unavailable")


class InterfaceTests(unittest.TestCase):
    def test_many_interfaces_keep_raw_names_without_thrashing_the_label_cache(self):
        _interface_label.cache_clear()
        self.addCleanup(_interface_label.cache_clear)
        available = [(index, f"net{index}") for index in range(LIMITS.network_interface_labels + 1)]
        with patch("xray.network.capture.socket.if_nameindex", return_value=available):
            first = interface_labels()
            second = interface_labels()
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(available))
        self.assertEqual(_interface_label.cache_info().misses, LIMITS.network_interface_labels)
        self.assertEqual(_interface_label.cache_info().hits, LIMITS.network_interface_labels)
        self.assertEqual(first[available[-1][1]], available[-1][1])

    def test_interface_labels_use_kernel_metadata_and_keep_unknown_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [
                ("local0", "772", "", "local0 · This machine"),
                ("custom0", "1", "wireless", "custom0 · Wi-Fi"),
                ("lan0", "1", "device", "lan0 · Ethernet"),
                ("docker0", "1", "bridge", "docker0 · Docker network"),
                ("bridge0", "1", "bridge", "bridge0 · Network bridge"),
                ("unknown0", "1", "", "unknown0"),
            ]
            for index, (name, kind, marker, expected) in enumerate(cases):
                with self.subTest(name=name):
                    path = root / name
                    path.mkdir()
                    (path / "type").write_text(kind)
                    if marker:
                        (path / marker).mkdir()
                    self.assertEqual(_interface_label(index, name, root), expected)


class NamesTests(unittest.TestCase):
    def test_opt_in_lookup_is_nonblocking_bounded_cached_and_clearable(self):
        started = threading.Event()
        release = threading.Event()

        def lookup(argv, **kwargs):
            self.assertEqual(kwargs["timeout_seconds"], TIMING.network_name_seconds)
            started.set()
            release.wait(2)
            return CommandResult(tuple(argv), 0, argv[-1] + " resolved.example\n", "")

        runner = Mock()
        runner.run.side_effect = lookup
        names = DestinationNames(runner)
        self.addCleanup(names.close)
        self.addCleanup(release.set)
        addresses = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
        self.assertEqual(names.resolve(addresses), {})
        runner.run.assert_not_called()
        names.enabled = True
        self.assertEqual(names.resolve(addresses), {})
        self.assertTrue(started.wait(1))
        self.assertEqual(len(names._pending), 2)
        release.set()
        wait_for(lambda: all(f.done() for f in names._pending.values()))
        self.assertEqual(
            names.resolve(addresses[:2]),
            {address: "resolved.example" for address in addresses[:2]},
        )
        self.assertEqual(runner.run.call_count, 2)
        names.resolve(addresses[:2])
        self.assertEqual(runner.run.call_count, 2)
        names.close()
        self.assertEqual(names.resolve(addresses), {})
        self.assertEqual(names._cache, {})

    def test_failed_lookups_are_cached_and_retry_after_expiry(self):
        runner = Mock()
        runner.run.return_value = CommandResult((), 2, "", "not found")
        names = DestinationNames(runner)
        self.addCleanup(names.close)
        names.enabled = True
        names.resolve(["1.1.1.1"])
        wait_for(lambda: all(f.done() for f in names._pending.values()))
        self.assertEqual(names.resolve(["1.1.1.1"]), {"1.1.1.1": ""})
        self.assertEqual(runner.run.call_count, 1)
        names._cache["1.1.1.1"] = (
            time.monotonic() - TIMING.network_name_ttl_seconds - 1,
            "",
        )
        names.resolve(["1.1.1.1"])
        wait_for(lambda: runner.run.call_count == 2)

    def test_large_name_sets_do_not_requery_evicted_entries(self):
        from concurrent.futures import Future

        runner = Mock()
        names = DestinationNames(runner)
        self.addCleanup(names.close)
        names.enabled = True
        pool = Mock()

        def done(*args):
            future = Future()
            future.set_result("")
            return future

        pool.submit.side_effect = done
        names._pool = pool
        addresses = [f"10.0.{index // 256}.{index % 256}" for index in range(300)]
        for _ in range(300):
            names.resolve(addresses)
        self.assertEqual(pool.submit.call_count, LIMITS.network_name_cache)
        self.assertEqual(len(names._cache), LIMITS.network_name_cache)


class MonitorTests(unittest.TestCase):
    def test_counters_are_never_read_from_host_for_an_alternate_procfs(self):
        proc = Mock(root=Path("/fixture-proc"))
        proc.readlink.return_value.value = NAMESPACE
        monitor = NetworkMonitor(proc, Mock())
        self.addCleanup(monitor.close)
        with patch("xray.network.traffic.tcp_counters") as collect:
            result = monitor.sample([connection()], [PROCESS], (), 300)
        collect.assert_not_called()
        self.assertIn(
            "TCP counters are unavailable for this procfs source", result["limited"]
        )

    def test_empty_udp_and_foreign_namespace_targets_skip_tcp_dump(self):
        proc = Mock(root=Path("/proc"))
        proc.readlink.return_value.value = NAMESPACE
        monitor = NetworkMonitor(proc, Mock())
        self.addCleanup(monitor.close)
        with patch(
            "xray.network.traffic.tcp_counters", return_value=({}, [])
        ) as collect:
            for rows in (
                [],
                [connection(protocol="UDP4")],
                [connection(networkNamespace="net:[999]")],
            ):
                monitor.sample(rows, [PROCESS], (), 300)
            collect.assert_not_called()
            monitor.sample([connection()], [PROCESS], (), 300)
            collect.assert_called_once_with((socket.AF_INET,))
