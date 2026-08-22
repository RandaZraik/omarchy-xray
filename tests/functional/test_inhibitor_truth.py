import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest

from live_backend import LiveBackend

from xray.devices.inhibitors import collect_inhibitors
from xray.system.commands import CommandRunner


@unittest.skipUnless(shutil.which("systemd-inhibit"), "requires systemd-inhibit")
class InhibitorTruthTests(unittest.TestCase):
    def test_live_inhibitor_matches_systemds_json_oracle(self) -> None:
        available = subprocess.run(
            ["systemd-inhibit", "--list", "--json=short"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if available.returncode != 0:
            self.skipTest("the systemd inhibitor API is unavailable")
        marker = f"Omarchy X-Ray test {os.getpid()}-{time.monotonic_ns()}"
        process = subprocess.Popen(
            [
                "systemd-inhibit",
                "--what=sleep",
                f"--who={marker}",
                "--why=Verify live ownership",
                "--mode=block",
                "sleep",
                "30",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 5
            oracle = None
            stable_pid = 0
            stable_reads = 0
            while time.monotonic() < deadline:
                completed = subprocess.run(
                    ["systemd-inhibit", "--list", "--json=short"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                entries = json.loads(completed.stdout)
                oracle = next(
                    (row for row in entries if row.get("who") == marker),
                    None,
                )
                observed_pid = int(oracle["pid"]) if oracle else 0
                if observed_pid and observed_pid == stable_pid:
                    stable_reads += 1
                else:
                    stable_pid = observed_pid
                    stable_reads = 1 if observed_pid else 0
                if stable_reads >= 3:
                    break
                time.sleep(0.05)
            self.assertIsNotNone(oracle)
            self.assertGreaterEqual(stable_reads, 3)
            owner_pid = int(oracle["pid"])

            rows, error = collect_inhibitors(CommandRunner(), [owner_pid])
            self.assertEqual(error, "")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["pid"], owner_pid)
            self.assertEqual(rows[0]["what"], "sleep")
            self.assertEqual(rows[0]["who"], marker)
            self.assertEqual(rows[0]["why"], "Verify live ownership")
            self.assertEqual(rows[0]["mode"], "block")

            with (
                TemporaryDirectory() as directory,
                LiveBackend(Path(directory)) as backend,
            ):
                response = backend.request("inspect", query=f"pid:{owner_pid}")
                self.assertTrue(response["ok"], response)
                snapshot = response["data"]
                snapshot_rows = snapshot["devices"]["inhibitors"]

            current = json.loads(
                subprocess.run(
                    ["systemd-inhibit", "--list", "--json=short"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
            )
            selected_pids = {row["pid"] for row in snapshot["processes"]}
            expected = [
                {
                    "pid": int(row["pid"]),
                    "what": row["what"],
                    "who": row["who"],
                    "why": row["why"],
                    "mode": row["mode"],
                }
                for row in current
                if row.get("who") == marker and int(row["pid"]) in selected_pids
            ]
            self.assertEqual(snapshot_rows, expected)
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
