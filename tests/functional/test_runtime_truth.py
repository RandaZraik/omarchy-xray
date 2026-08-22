from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest

from live_backend import LiveBackend, wait_until


HAS_SYSTEMD_USER = bool(shutil.which("systemctl") and shutil.which("systemd-run"))
HAS_DOCKER = bool(shutil.which("docker"))


class RuntimeTruthTests(unittest.TestCase):
    def require_ok(self, response: dict[str, object]) -> dict[str, object]:
        self.assertTrue(response.get("ok"), response)
        data = response.get("data")
        self.assertIsInstance(data, dict)
        return data

    @unittest.skipUnless(
        shutil.which("systemctl") and shutil.which("journalctl"),
        "requires systemd and journalctl",
    )
    def test_system_service_logs_match_the_system_journal_scope(self) -> None:
        unit = "systemd-logind.service"
        shown = subprocess.run(
            ["systemctl", "show", unit, "--property=MainPID", "--value"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            check=False,
        )
        pid = int(shown.stdout.strip() or 0)
        if not pid or not Path(f"/proc/{pid}/stat").exists():
            self.skipTest(f"{unit} is not active")
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        uptime = float(Path("/proc/uptime").read_text().split()[0])
        started = int(
            max(0, time.time() - uptime + int(stat[19]) / os.sysconf("SC_CLK_TCK"))
        )
        with TemporaryDirectory() as directory, LiveBackend(Path(directory)) as backend:
            snapshot = self.require_ok(
                backend.request("inspect", query=f"service:system:{unit}")
            )
        oracle = subprocess.run(
            [
                "journalctl",
                f"--unit={unit}",
                f"--since=@{started}",
                "--no-pager",
                "--output=json",
                "--lines",
                "50",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=4,
            check=False,
        )
        if oracle.returncode not in (0, 1) or not oracle.stdout.strip():
            self.skipTest("no readable system journal rows exist for logind")
        expected_timestamps = {
            str(json.loads(line).get("__REALTIME_TIMESTAMP", ""))
            for line in oracle.stdout.splitlines()
        }

        self.assertEqual(snapshot["context"]["service"]["scope"], "system")
        self.assertTrue(snapshot["logs"])
        self.assertTrue(
            all(row["timestamp"] in expected_timestamps for row in snapshot["logs"])
        )
        self.assertIn("Journal entries", snapshot["coverage"]["available"])

    @unittest.skipUnless(HAS_SYSTEMD_USER, "requires user and system systemd managers")
    def test_same_named_user_and_system_services_resolve_to_their_exact_scope(
        self,
    ) -> None:
        unit = "dbus-broker.service"

        def main_pid(scope: str) -> int:
            command = ["systemctl"]
            if scope == "user":
                command.append("--user")
            shown = subprocess.run(
                [*command, "show", unit, "--property=MainPID", "--value"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
                check=False,
            )
            return int(shown.stdout.strip() or 0)

        expected = {scope: main_pid(scope) for scope in ("user", "system")}
        if not all(expected.values()) or expected["user"] == expected["system"]:
            self.skipTest(f"{unit} is not active in both scopes")

        with TemporaryDirectory() as directory, LiveBackend(Path(directory)) as backend:
            for scope in ("user", "system"):
                with self.subTest(scope=scope):
                    snapshot = self.require_ok(
                        backend.request("inspect", query=f"service:{scope}:{unit}")
                    )
                    self.assertEqual(snapshot["target"]["ownerPid"], expected[scope])
                    self.assertEqual(snapshot["context"]["service"]["scope"], scope)

    @unittest.skipUnless(HAS_SYSTEMD_USER, "requires a user systemd manager")
    def test_user_service_query_matches_systemd_main_pid_unit_and_cause(self) -> None:
        unit = f"omarchy-xray-truth-{os.getpid()}.service"
        launched = subprocess.run(
            [
                "systemd-run",
                "--user",
                f"--unit={unit}",
                "--property=Type=simple",
                "--property=Restart=always",
                "--property=RestartSec=2",
                "sleep",
                "120",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
        if launched.returncode != 0:
            self.skipTest(launched.stderr.strip() or "user systemd is unavailable")
        self.addCleanup(
            subprocess.run,
            ["systemctl", "--user", "stop", unit],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )

        def main_pid() -> int:
            shown = subprocess.run(
                ["systemctl", "--user", "show", unit, "--property=MainPID", "--value"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
                check=False,
            )
            return int(shown.stdout.strip() or 0)

        self.assertTrue(wait_until(lambda: main_pid() > 0))
        expected_pid = main_pid()
        with TemporaryDirectory() as directory, LiveBackend(Path(directory)) as backend:
            snapshot = self.require_ok(
                backend.request("inspect", query=f"pid:{expected_pid}")
            )
            self.assertEqual(snapshot["target"]["ownerPid"], expected_pid)
            self.assertEqual(snapshot["context"]["service"]["id"], unit)
            self.assertEqual(snapshot["context"]["service"]["scope"], "user")
            self.assertEqual(snapshot["context"]["cause"]["status"], "Confirmed")
            self.assertTrue(
                any(
                    node["kind"] == "service" and node["title"] == unit
                    for node in snapshot["context"]["cause"]["nodes"]
                )
            )
            relaunch = next(
                action for action in snapshot["actions"] if action["id"] == "relaunch"
            )
            self.assertTrue(relaunch["available"])
            restarted = self.require_ok(
                backend.request(
                    "action",
                    action="relaunch",
                    inspectionId=snapshot["target"]["inspectionId"],
                )
            )
            self.assertTrue(restarted["ok"], restarted)
            self.assertTrue(wait_until(lambda: main_pid() not in {0, expected_pid}))
            replacement_pid = main_pid()
            replacement = self.require_ok(backend.request("refresh"))
            self.assertEqual(replacement["target"]["ownerPid"], replacement_pid)
            self.assertEqual(replacement["target"]["kind"], "service")
            self.assertEqual(replacement["target"]["value"], f"user:{unit}")

            os.kill(replacement_pid, signal.SIGKILL)
            self.assertTrue(wait_until(lambda: main_pid() == 0))
            missing = self.require_ok(backend.request("refresh"))
            self.assertEqual(missing["target"]["rootPid"], 0)
            self.assertEqual(missing["target"]["kind"], "service")

            self.assertTrue(
                wait_until(lambda: main_pid() not in {0, replacement_pid}, timeout=5.0)
            )

            recovered: dict[str, object] = {}

            def refresh_recovered() -> bool:
                nonlocal recovered
                recovered = self.require_ok(backend.request("refresh"))
                return int(recovered["target"]["rootPid"]) == main_pid()

            self.assertTrue(wait_until(refresh_recovered))

    @unittest.skipUnless(HAS_DOCKER, "requires Docker")
    def test_container_query_and_restart_match_a_dedicated_docker_oracle(self) -> None:
        image = "python:3.12-slim"
        available = subprocess.run(
            ["docker", "image", "inspect", image],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
        if available.returncode != 0:
            self.skipTest(f"the local {image} test image is unavailable")
        name = f"omarchy-xray-truth-{os.getpid()}"
        launched = subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                "--network",
                "none",
                image,
                "python",
                "-c",
                "import time; time.sleep(120)",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        if launched.returncode != 0:
            self.skipTest(launched.stderr.strip() or "could not start test container")
        self.addCleanup(
            subprocess.run,
            ["docker", "rm", "--force", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )

        def inspect_container() -> dict[str, object]:
            shown = subprocess.run(
                ["docker", "inspect", name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=True,
            )
            return json.loads(shown.stdout)[0]

        raw = inspect_container()
        expected_pid = int(raw["State"]["Pid"])

        with TemporaryDirectory() as directory, LiveBackend(Path(directory)) as backend:
            snapshot = self.require_ok(
                backend.request("inspect", query=f"container:docker:{name}")
            )
            container = snapshot["context"]["container"]
            self.assertEqual(snapshot["target"]["ownerPid"], expected_pid)
            self.assertEqual(container["name"], name)
            self.assertEqual(container["image"], image)
            self.assertEqual(container["runtime"], "docker")
            relaunch = next(
                action for action in snapshot["actions"] if action["id"] == "relaunch"
            )
            self.assertTrue(relaunch["available"])
            self.assertTrue(
                any(
                    node["kind"] == "container" and node["pid"] == expected_pid
                    for node in snapshot["context"]["cause"]["nodes"]
                )
            )

            restarted = self.require_ok(
                backend.request(
                    "action",
                    action="relaunch",
                    inspectionId=snapshot["target"]["inspectionId"],
                )
            )
            self.assertTrue(restarted["ok"], restarted)
            replacement_pid = int(inspect_container()["State"]["Pid"])
            self.assertGreater(replacement_pid, 0)
            self.assertNotEqual(replacement_pid, expected_pid)

            refreshed: dict[str, object] = {}

            def recovered() -> bool:
                nonlocal refreshed
                refreshed = self.require_ok(backend.request("refresh"))
                return refreshed["target"]["ownerPid"] == replacement_pid

            self.assertTrue(wait_until(recovered, timeout=5))


if __name__ == "__main__":
    unittest.main()
