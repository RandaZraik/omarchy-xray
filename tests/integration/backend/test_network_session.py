from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from support.live_backend import LiveBackend
from support.network_live import TcpFixture


class LiveNetworkTests(unittest.TestCase):
    def test_known_size_upload_download_v4_v6_pause_history_and_export(self):
        for ipv6 in (False, True):
            with (
                self.subTest(ipv6=ipv6),
                TemporaryDirectory() as directory,
                TcpFixture(ipv6) as fixture,
                LiveBackend(Path(directory) / "state") as backend,
            ):

                def request(command, **fields):
                    response = backend.request(command, **fields)
                    self.assertTrue(response["ok"], response)
                    return response["data"]

                first = request("inspect", query=f"pid:{fixture.process.pid}")
                root_id = first["target"]["inspectionId"]
                flow = next(
                    row
                    for row in first["network"]["flows"]
                    if row["remotePort"] == fixture.port
                )
                self.assertEqual(flow["sampleStatus"], "baseline")
                self.assertEqual(flow["owners"][0]["pid"], fixture.process.pid)
                fixture.transfer("send", 262144)
                fixture.transfer("receive", 131072)
                deadline = time.monotonic() + 2
                while True:
                    snapshot = request("refresh")
                    flow = next(
                        row
                        for row in snapshot["network"]["flows"]
                        if row["remotePort"] == fixture.port
                    )
                    if flow["sentBytes"] == 262144 or time.monotonic() >= deadline:
                        break
                    time.sleep(0.03)
                self.assertEqual(flow["sentBytes"], 262144)
                self.assertEqual(flow["receivedBytes"], 131072)
                self.assertEqual(snapshot["network"]["totals"]["sentBytes"], 262144)
                self.assertEqual(snapshot["network"]["totals"]["receivedBytes"], 131072)
                self.assertGreater(flow["sampleSeconds"], 0)
                self.assertEqual(flow["scope"], "loopback")

                idle = request("refresh", compact=True)["snapshotPatch"]
                self.assertIn("network", idle)
                idle_flow = next(
                    row
                    for row in idle["network"]["flows"]
                    if row["remotePort"] == fixture.port
                )
                self.assertEqual(idle_flow["sentRate"], 0)
                self.assertEqual(idle_flow["receivedRate"], 0)
                request("setSamplingPaused", paused=True)
                fixture.transfer("send", 1024)
                paused = request("refresh")
                self.assertEqual(paused["network"]["totals"]["sentBytes"], 262144)
                request("setSamplingPaused", paused=False)
                resumed = request("refresh")
                self.assertIsNone(resumed["network"]["totals"]["sentRate"])
                self.assertEqual(resumed["network"]["totals"]["sentBytes"], 262144)
                saved = request("exportCapsule", directory=directory)
                loaded = request("openCapsule", path=saved["path"])["snapshot"]
                self.assertEqual(loaded["network"], resumed["network"])

                bad = backend.request(
                    "configureNetwork", inspectionId=root_id + 1, resolveNames=True
                )
                self.assertFalse(bad["ok"])
                bad = backend.request(
                    "configureNetwork",
                    inspectionId=root_id,
                    capture=True,
                    interface="not-an-interface",
                )
                self.assertFalse(bad["ok"])

                fixture.peer.close()
                fixture.process.terminate()
                fixture.process.wait(timeout=3)
                empty = request("refresh")
                self.assertFalse(empty.get("network", {}).get("flows", []))
