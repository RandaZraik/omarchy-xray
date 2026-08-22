from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from live_backend import LiveBackend, wait_until

from xray.devices.pipewire import collect_pipewire
from xray.system.commands import CommandRunner
from xray.system.procfs import ProcFs
from xray.targets.catalog import TargetCatalog
from xray.targets.query import TargetSpec
from xray.targets.resolver import TargetResolver


HAS_PIPEWIRE_TOOLS = bool(shutil.which("pw-cat") and shutil.which("pw-dump"))


@unittest.skipUnless(HAS_PIPEWIRE_TOOLS, "requires PipeWire command-line tools")
class PipeWireTruthTests(unittest.TestCase):
    def test_silent_live_stream_resolves_to_its_real_process(self) -> None:
        player = subprocess.Popen(
            [
                "pw-cat",
                "--playback",
                "--raw",
                "--rate",
                "48000",
                "--channels",
                "2",
                "/dev/zero",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        runner = CommandRunner()
        try:
            observed: list[dict[str, object]] = []

            def stream_visible() -> bool:
                nonlocal observed
                observed, _ = collect_pipewire(runner, [player.pid])
                return any(
                    row["pid"] == player.pid and row["active"] for row in observed
                )

            self.assertTrue(
                wait_until(stream_visible),
                "PipeWire never exposed the known silent stream",
            )
            row = next(row for row in observed if row["pid"] == player.pid)
            self.assertEqual(row["kind"], "audio")
            self.assertEqual(row["state"], "Running")

            resolver = TargetResolver(ProcFs(), runner)
            resolved = resolver.resolve(TargetSpec("device", "audio", "Audio activity"))
            self.assertIn(player.pid, {item["pid"] for item in resolved.alternatives})
            catalog = TargetCatalog(
                resolver.proc,
                resolver.runner,
                resolver.systemd,
                resolver.containers,
            ).collect()
            self.assertTrue(any(row["pid"] == player.pid for row in catalog["devices"]))
            with (
                TemporaryDirectory() as directory,
                LiveBackend(Path(directory)) as backend,
            ):
                response = backend.request("inspect", query=f"pid:{player.pid}")
                self.assertTrue(response["ok"], response)
                snapshot_rows = response["data"]["devices"]["pipewire"]
            live = next(row for row in snapshot_rows if row["pid"] == player.pid)
            self.assertEqual(live["kind"], "audio")
            self.assertTrue(live["active"])
        finally:
            player.terminate()
            try:
                player.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                player.kill()
                player.wait(timeout=3.0)


if __name__ == "__main__":
    unittest.main()
