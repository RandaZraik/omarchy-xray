from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from support.live_backend import LiveBackend


class PerformanceSessionTests(unittest.TestCase):
    def test_refresh_pause_target_switch_and_capsule_preserve_measurements(
        self,
    ) -> None:
        with (
            TemporaryDirectory() as directory,
            LiveBackend(Path(directory) / "state") as backend,
        ):
            first = subprocess.Popen(["sleep", "60"])
            second = subprocess.Popen(["sleep", "60"])
            for process in (first, second):
                self.addCleanup(process.wait, timeout=3)
                self.addCleanup(process.terminate)

            def request(command: str, **fields: object) -> dict[str, object]:
                response = backend.request(command, **fields)
                self.assertTrue(response.get("ok"), response)
                return response["data"]

            def work(snapshot: dict[str, object]) -> dict[str, object]:
                return next(
                    row
                    for row in snapshot["performance"]["checks"]
                    if row["id"] == "performance-cpu-work"
                )

            snapshot = request("inspect", query=f"pid:{first.pid}")
            self.assertEqual(work(snapshot)["status"], "Baseline")
            patch = request("refresh", compact=True)["snapshotPatch"]
            self.assertIn("performance", patch)
            snapshot.update(patch)
            self.assertEqual(work(snapshot)["status"], "Quiet")
            self.assertEqual(work(snapshot)["measurements"]["processes"], 1)
            self.assertIn("performance", snapshot["coverage"]["domains"])

            request("setSamplingPaused", paused=True)
            paused = request("refresh")
            self.assertEqual(paused["performance"], snapshot["performance"])
            request("setSamplingPaused", paused=False)
            resumed = request("refresh")
            self.assertEqual(work(resumed)["status"], "Baseline")
            request("refresh")
            switched = request("inspect", query=f"pid:{second.pid}")
            self.assertEqual(work(switched)["status"], "Baseline")
            measured = request("refresh")

            exported = request("exportCapsule", directory=directory)
            loaded = request("openCapsule", path=exported["path"])["snapshot"]
            self.assertEqual(loaded["performance"], measured["performance"])
            report = request("report")["text"]
            self.assertIn("Why slow?", report)
            for check in measured["performance"]["checks"]:
                self.assertIn(f"[{check['status']}] {check['title']}", report)

            second.terminate()
            second.wait(timeout=3)
            empty = request("refresh")
            self.assertEqual(empty["performance"]["status"], "unavailable")
            self.assertEqual(empty["performance"]["checks"], [])
