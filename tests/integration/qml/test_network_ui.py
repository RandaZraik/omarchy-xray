import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import threading
from support.network_live import TcpFixture

from support.network import NAMESPACE, PROCESS, connection, counter
from support.quickshell import QuickshellHarness
from xray.network.traffic import TrafficHistory


HARNESS = QuickshellHarness()
ORACLE = Path(__file__).with_name("oracles") / "network_oracle.qml"


def network_snapshot() -> dict[str, object]:
    processes = [
        {**PROCESS, "name": "browser"},
        {**PROCESS, "pid": 43, "name": "network-service"},
    ]
    endpoints = [
        ("1.1.1.1", 443, "TCP4"),
        ("8.8.8.8", 443, "TCP4"),
        ("192.168.1.1", 8443, "TCP4"),
        ("127.0.0.1", 5173, "TCP4"),
        ("2606:4700:4700::1111", 443, "TCP6"),
        ("224.0.0.251", 5353, "UDP4"),
    ]
    sockets = [
        connection(
            inode=index + 1,
            remoteAddress=address,
            remotePort=port,
            protocol=protocol,
            state="Open" if protocol.startswith("UDP") else "Established",
            pids=[42] if index < 2 else [43],
            localPort=41000 + index,
        )
        for index, (address, port, protocol) in enumerate(endpoints)
    ]
    history = TrafficHistory()
    before = {
        int(row["inode"]): counter(
            10,
            20,
            inode=int(row["inode"]),
            cookie=str(row["inode"]),
            local_port=int(row["localPort"]),
            remote_address=str(row["remoteAddress"]),
            remote_port=int(row["remotePort"]),
        )
        for row in sockets
        if str(row["protocol"]).startswith("TCP")
    }
    history.update(sockets, processes, before, NAMESPACE, now=1000, monotonic=1)
    after = {
        key: __import__("dataclasses").replace(
            value, sent=value.sent + 4096 * key, received=value.received + 8192 * key
        )
        for key, value in before.items()
    }
    network = history.update(
        sockets, processes, after, NAMESPACE, now=1002, monotonic=3
    )
    network["capture"] = {
        "active": False,
        "interfaces": ["lo", "eth0", "docker0"],
        "interfaceLabels": {"lo": "lo · This machine", "eth0": "eth0 · Ethernet", "docker0": "docker0 · Docker network"},
        "error": "",
    }
    network["limited"] = ["UDP traffic rates need packet capture"]
    network["events"].append(
        {
            "kind": "closed",
            "at": 1001,
            "flowId": "ended",
            "protocol": "TCP4",
            "address": "1.0.0.1",
            "port": 443,
            "owners": processes[:1],
        }
    )
    return {
        "target": {"rootPid": 42, "label": "Example browser"},
        "processes": processes,
        "connections": sockets,
        "network": network,
        "settings": {"historySeconds": 60},
    }


@unittest.skipUnless(
    HARNESS.executable and HARNESS.imports.is_dir(),
    "requires Quickshell and Omarchy imports",
)
class NetworkUiTests(unittest.TestCase):
    def test_real_transfers_reach_the_open_map_through_the_controller(self):
        resolver = subprocess.run(
            ["getent", "hosts", "127.0.0.1"], capture_output=True, text=True, timeout=3
        )
        self.assertEqual(resolver.returncode, 0, resolver.stderr)
        expected_name = resolver.stdout.split()[1]
        capture_required = os.environ.get("XRAY_NETWORK_ISOLATED") == "1"
        with TcpFixture() as fixture, TemporaryDirectory() as directory:
            stop = threading.Event()
            errors = []

            def transfer():
                try:
                    while not stop.wait(0.2):
                        fixture.transfer("send", 65536)
                        fixture.transfer("receive", 32768)
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=transfer, daemon=True)
            root = Path(directory)
            shell = HARNESS.stage_plugin(
                root, ORACLE.with_name("network_live_oracle.qml"), include_backend=True
            )
            worker.start()
            try:
                result = HARNESS.run_offscreen(
                    shell,
                    timeout=30,
                    state_home=root / "state",
                    environment={
                        "XRAY_CAPTURE_REQUIRED": "1" if capture_required else "0",
                        "XRAY_EXPECTED_NAME": expected_name,
                        "XRAY_LIVE_PID": str(fixture.process.pid),
                        "XRAY_LIVE_PORT": str(fixture.port),
                    },
                )
            finally:
                stop.set()
                worker.join(timeout=6)
            self.assertFalse(errors)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result.returncode, 0, result.output)
            marker = result.json_marker("XRAY_NETWORK_LIVE")
            self.assertTrue(marker["visible"])
            self.assertEqual(marker["mode"], "tcp")
            self.assertGreater(marker["sent"], 0)
            self.assertGreater(marker["received"], 0)
            for key in ("copy", "nameLookup", "owner", "filters", "history"):
                self.assertTrue(marker[key])
            self.assertIn(
                marker["capture"],
                ("live packet rates",)
                if capture_required
                else ("live packet rates", "live permission failure"),
            )

    def test_map_search_filters_evidence_history_offline_and_refresh(self):
        for width, height in ((600, 600), (600, 900), (820, 900)):
            with (
                self.subTest(width=width, height=height),
                TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                shell = HARNESS.stage_plugin(root, ORACLE)
                result = HARNESS.run_offscreen(
                    shell,
                    timeout=15,
                    state_home=root / "state",
                    environment={
                        "XRAY_NETWORK_FIXTURE": json.dumps(network_snapshot()),
                        "XRAY_NETWORK_WIDTH": str(width),
                        "XRAY_NETWORK_HEIGHT": str(height),
                    },
                )
                self.assertEqual(result.returncode, 0, result.output)
                marker = result.json_marker("XRAY_NETWORK_UI")
                for key in (
                    "map",
                    "search",
                    "filters",
                    "evidence",
                    "history",
                    "sockets",
                    "offline",
                    "refresh",
                ):
                    self.assertTrue(marker[key])
                for error in (
                    "TypeError",
                    "ReferenceError",
                    "Binding loop",
                    "Unable to assign",
                ):
                    self.assertNotIn(error, result.output)
