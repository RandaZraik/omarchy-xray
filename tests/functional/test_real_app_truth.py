from __future__ import annotations

import json
import math
import os
from pathlib import Path
import pwd
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest

from live_backend import LiveBackend
from machine_truth import (
    descriptor_mode,
    descriptor_targets,
    hyprland_clients,
    proc_stat,
    proc_status,
    raw_drm_clients,
    raw_locks,
    raw_pipewire_streams,
    raw_socket_inventory,
    rendered_details,
)
from xray.evidence.redaction import redact_command


HAS_DESKTOP = bool(
    os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    and shutil.which("hyprctl")
    and (shutil.which("qml6") or shutil.which("qml"))
)


@unittest.skipUnless(HAS_DESKTOP, "requires the live Omarchy desktop")
class RealApplicationTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        clients = hyprland_clients()
        cls.windows = {}
        for label, predicate in (
            ("Chromium", lambda row: "chromium" in str(row.get("class", "")).lower()),
            ("terminal", lambda row: "ghostty" in str(row.get("class", "")).lower()),
        ):
            cls.windows[label] = next((row for row in clients if predicate(row)), None)
        missing = [name for name, row in cls.windows.items() if row is None]
        if missing:
            raise AssertionError(
                f"live truth targets are missing: {', '.join(missing)}"
            )
        cls.state = TemporaryDirectory(prefix=".xray-app-truth-", dir=Path.home())
        cls.backend = LiveBackend(Path(cls.state.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.backend.close()
        cls.state.cleanup()

    def inspect_window(self, label: str) -> dict[str, object]:
        address = self.windows[label]["address"]
        response = self.backend.request("inspect", query=f"window:{address}")
        self.assertTrue(response["ok"], response)
        initial_pids = [int(row["pid"]) for row in response["data"]["processes"]]
        time.sleep(0.25)
        self.truth_before = self._live_domains(initial_pids)
        refreshed = self.backend.request("refresh")
        self.assertTrue(refreshed["ok"], refreshed)
        refreshed_pids = [int(row["pid"]) for row in refreshed["data"]["processes"]]
        self.truth_after = self._live_domains(refreshed_pids)
        return refreshed["data"]

    @staticmethod
    def _live_domains(pids: list[int]) -> dict[str, object]:
        processes: dict[int, dict[str, object]] = {}
        for pid in pids:
            try:
                raw_command = Path(f"/proc/{pid}/cmdline").read_bytes()
                processes[pid] = {
                    "stat": proc_stat(pid),
                    "status": proc_status(pid),
                    "command": redact_command(
                        [
                            part.decode("utf-8", errors="replace")
                            for part in raw_command.split(b"\0")
                            if part
                        ]
                    ),
                    "executable": os.readlink(f"/proc/{pid}/exe"),
                    "cwd": os.readlink(f"/proc/{pid}/cwd"),
                }
            except OSError:
                continue
        return {
            "processes": processes,
            "connections": raw_socket_inventory(pids),
            "files": {
                (pid, fd, target)
                for pid in pids
                for fd, target in descriptor_targets(pid).items()
            },
            "locks": {row for row in raw_locks() if row[3] in set(pids)},
            "pipewire": {
                key: value
                for key, value in raw_pipewire_streams().items()
                if key[1] in set(pids)
            },
            "gpu": raw_drm_clients(pids),
        }

    def test_every_card_and_drilldown_matches_live_terminal_and_chromium(self) -> None:
        for label, expected_window in self.windows.items():
            with self.subTest(application=label):
                snapshot = self.inspect_window(label)
                self._assert_identity(snapshot, expected_window)
                pids = self._assert_processes_and_performance(snapshot)
                self._assert_connections(snapshot, pids)
                self._assert_files_and_locks(snapshot)
                self._assert_devices(snapshot, pids)
                self._assert_runtime_and_cause(snapshot)
                self._assert_explanations(snapshot)
                self._assert_every_drilldown(snapshot)

    def _assert_identity(
        self, snapshot: dict[str, object], expected_window: dict[str, object]
    ) -> None:
        target = snapshot["target"]
        context = snapshot["context"]
        window = context["window"]
        root_pid = int(target["rootPid"])
        self.assertEqual(target["ownerPid"], expected_window["pid"])
        self.assertEqual(root_pid, expected_window["pid"])
        for key in ("address", "pid", "class"):
            self.assertEqual(window[key], expected_window[key])
        if "ghostty" in str(window["class"]).lower():
            self.assertEqual(
                str(window["title"]).partition(" ")[2],
                str(expected_window["title"]).partition(" ")[2],
            )
        else:
            self.assertEqual(window["title"], expected_window["title"])
        self.assertEqual(window["workspace"], expected_window["workspace"])
        self.assertEqual(context["executable"], os.readlink(f"/proc/{root_pid}/exe"))
        self.assertEqual(
            context["workingDirectory"], os.readlink(f"/proc/{root_pid}/cwd")
        )
        self.assertNotIn("oauth2-client-secret=OTJ", json.dumps(snapshot))

    def _assert_processes_and_performance(
        self, snapshot: dict[str, object]
    ) -> list[int]:
        rows = snapshot["processes"]
        metrics = snapshot["metrics"]
        self.assertGreater(len(rows), 0)
        pids = [int(row["pid"]) for row in rows]
        self.assertEqual(metrics["processCount"], len(rows))
        self.assertEqual(
            metrics["memoryBytes"], sum(int(row["memoryBytes"]) for row in rows)
        )
        self.assertEqual(metrics["threads"], sum(int(row["threads"]) for row in rows))
        if metrics["cpuAvailable"]:
            self.assertGreaterEqual(float(metrics["cpuPercent"]), 0)
            self.assertLessEqual(float(metrics["cpuPercent"]), 100)
        else:
            self.assertIsNone(metrics["cpuPercent"])
            self.assertEqual(metrics["cpuStatus"], "baseline")
            self.assertTrue(
                any(
                    "CPU activity is collecting a baseline" in message
                    for message in snapshot["coverage"]["limited"]
                )
            )
        if metrics["gpuPercent"] is not None:
            self.assertGreaterEqual(float(metrics["gpuPercent"]), 0)
            self.assertLessEqual(float(metrics["gpuPercent"]), 100)

        verified = 0
        for row in rows:
            pid = int(row["pid"])
            candidates = [
                snapshot_row
                for source in (self.truth_before, self.truth_after)
                if (snapshot_row := source["processes"].get(pid)) is not None
            ]
            if not candidates:
                continue
            verified += 1
            stats = [candidate["stat"] for candidate in candidates]
            statuses = [candidate["status"] for candidate in candidates]
            self.assertIn(row["startTime"], {stat["startTime"] for stat in stats})
            self.assertIn(row["ppid"], {stat["ppid"] for stat in stats})
            self.assertIn(row["name"], {status["Name"] for status in statuses})
            # Process state can change between adjacent procfs reads, so only
            # validate the kernel state code instead of requiring a stale match.
            self.assertRegex(str(row["state"]), r"^[RSDTtZXIP]$")
            self.assertIn(
                row["uid"], {int(status["Uid"].split()[0]) for status in statuses}
            )
            self.assertEqual(row["user"], pwd.getpwuid(row["uid"]).pw_name)
            self.assertIn(
                row["gid"], {int(status["Gid"].split()[0]) for status in statuses}
            )
            self.assertIn(
                row["threads"], {int(status["Threads"]) for status in statuses}
            )
            memory_values = [int(stat["rssBytes"]) for stat in stats]
            self.assertGreaterEqual(
                int(row["memoryBytes"]), min(memory_values) - 4 * 1024 * 1024
            )
            self.assertLessEqual(
                int(row["memoryBytes"]), max(memory_values) + 4 * 1024 * 1024
            )
            self.assertIn(
                row["command"], [candidate["command"] for candidate in candidates]
            )
            self.assertIn(
                row["executable"],
                {candidate["executable"] for candidate in candidates},
            )
            self.assertIn(row["cwd"], {candidate["cwd"] for candidate in candidates})
            if row["cpuPercent"] is not None:
                self.assertGreaterEqual(float(row["cpuPercent"]), 0)
                self.assertLessEqual(float(row["cpuPercent"]), 100)
            for key in ("readBytesPerSecond", "writeBytesPerSecond"):
                if row[key] is not None:
                    self.assertGreaterEqual(float(row[key]), 0)
            self.assertTrue(all("=" not in name for name in row["environmentNames"]))
        self.assertGreaterEqual(verified, max(1, int(len(rows) * 0.9)))
        uptime = float(Path("/proc/uptime").read_text().split()[0])
        expected_uptime = max(
            0,
            round(uptime - int(rows[0]["startTime"]) / os.sysconf("SC_CLK_TCK")),
        )
        self.assertLessEqual(abs(int(metrics["uptimeSeconds"]) - expected_uptime), 2)
        return pids

    def _assert_connections(self, snapshot: dict[str, object], pids: list[int]) -> None:
        before = self.truth_before["connections"]
        after = self.truth_after["connections"]
        observed: set[tuple[object, ...]] = set()
        bracketing = [*before.items(), *after.items()]
        for row in snapshot["connections"]:
            key = (
                row["networkNamespace"],
                int(row["inode"]),
                row["protocol"],
                row["localAddress"],
                int(row["localPort"]),
                row["remoteAddress"],
                int(row["remotePort"]),
                row["state"],
            )
            observed.add(key)
            identity = key[:-1]
            matching_owners = [
                owners for candidate, owners in bracketing if candidate[:-1] == identity
            ]
            self.assertTrue(matching_owners, key)
            self.assertIn(
                set(row["pids"]),
                matching_owners,
            )
            expected_listening = row["state"] == "Listening" or (
                str(row["protocol"]).startswith("UDP") and int(row["remotePort"]) == 0
            )
            self.assertEqual(row["listening"], expected_listening)
            self.assertEqual(
                row["publicListener"],
                expected_listening and row["localAddress"] in {"0.0.0.0", "::"},
            )
        stable_identities = {key[:-1] for key in before} & {key[:-1] for key in after}
        self.assertTrue(
            stable_identities <= {key[:-1] for key in observed},
            "stable live sockets were omitted from the inspection",
        )

    def _assert_files_and_locks(self, snapshot: dict[str, object]) -> None:
        bracketed = self.truth_before["files"] | self.truth_after["files"]
        checked = 0
        for row in snapshot["files"]:
            pid = int(row["pid"])
            fd = int(row["fd"])
            target = str(row["target"])
            if (pid, fd, target) not in bracketed:
                continue
            checked += 1
            current_target = descriptor_targets(pid).get(fd)
            if current_target == target:
                mode = descriptor_mode(pid, fd)
                if mode is not None and "mode" in row:
                    self.assertEqual(row["mode"], mode)
            self.assertEqual(row["deleted"], target.endswith(" (deleted)"))
        self.assertGreaterEqual(checked, max(1, int(len(snapshot["files"]) * 0.8)))

        observed_files = {
            (int(row["pid"]), int(row["fd"]), str(row["target"]))
            for row in snapshot["files"]
        }
        stable_files = {
            row
            for row in self.truth_before["files"] & self.truth_after["files"]
            if str(row[2]).startswith("/")
        }
        observed_stable = stable_files & observed_files
        required_stable = math.ceil(len(stable_files) * 0.8)
        self.assertGreaterEqual(
            len(observed_stable),
            required_stable,
            "too many independently observed descriptors were omitted from Files & IPC",
        )

        observed_locks: set[tuple[object, ...]] = set()
        for row in snapshot["locks"]:
            key = (
                row["type"],
                row["scope"],
                row["mode"],
                int(row["pid"]),
                row["inode"],
                row["start"],
                row["end"],
            )
            observed_locks.add(key)
            self.assertIn(key, self.truth_before["locks"] | self.truth_after["locks"])
        self.assertTrue(
            self.truth_before["locks"] & self.truth_after["locks"] <= observed_locks,
            "stable kernel locks were omitted from Files & IPC",
        )

    def _assert_devices(self, snapshot: dict[str, object], pids: list[int]) -> None:
        devices = snapshot["devices"]
        observed_pipewire: set[tuple[int, int]] = set()
        for row in devices["pipewire"]:
            key = (int(row["id"]), int(row["pid"]))
            observed_pipewire.add(key)
            raw = self.truth_after["pipewire"].get(
                key, self.truth_before["pipewire"].get(key)
            )
            self.assertIsNotNone(raw)
            self.assertTrue(
                str(raw["props"].get("media.class", "")).startswith("Stream/")
            )
        observed_gpu: set[tuple[int, str, str]] = set()
        for row in devices["gpu"]:
            key = (int(row["pid"]), row["device"], str(row["clientId"]))
            observed_gpu.add(key)
            self.assertIn(key, self.truth_before["gpu"] | self.truth_after["gpu"])
            value = row.get("utilizationPercent")
            if value is not None:
                self.assertGreaterEqual(float(value), 0)
                self.assertLessEqual(float(value), 100)
        self.assertTrue(
            self.truth_before["pipewire"].keys() & self.truth_after["pipewire"].keys()
            <= observed_pipewire,
            "stable PipeWire streams were omitted from App device access",
        )
        self.assertTrue(
            self.truth_before["gpu"] & self.truth_after["gpu"] <= observed_gpu,
            "stable DRM clients were omitted from App device access",
        )

        if devices["inhibitors"]:
            completed = subprocess.run(
                ["systemd-inhibit", "--list", "--json=short"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            raw_rows = json.loads(completed.stdout)
            raw_keys = {
                (
                    int(row.get("pid", 0)),
                    str(row.get("what", "")),
                    str(row.get("why", "")),
                    str(row.get("mode", "")),
                )
                for row in raw_rows
            }
            for row in devices["inhibitors"]:
                self.assertIn(
                    (int(row["pid"]), row["what"], row["why"], row["mode"]), raw_keys
                )

    def _assert_runtime_and_cause(self, snapshot: dict[str, object]) -> None:
        root_pid = int(snapshot["target"]["rootPid"])
        context = snapshot["context"]
        security = snapshot["security"]
        status = proc_status(root_pid)
        self.assertEqual(security["uid"], int(status["Uid"].split()[0]))
        self.assertEqual(security["gid"], int(status["Gid"].split()[0]))
        self.assertEqual(security["noNewPrivileges"], status.get("NoNewPrivs") == "1")
        self.assertEqual(
            security["seccomp"],
            {"0": "Disabled", "1": "Strict", "2": "Filtered"}[status["Seccomp"]],
        )
        for name, namespace in security["namespaces"].items():
            self.assertEqual(namespace, os.readlink(f"/proc/{root_pid}/ns/{name}"))
        self.assertEqual(
            len(security["limits"]),
            len(Path(f"/proc/{root_pid}/limits").read_text().splitlines()) - 1,
        )

        service = context.get("service", {})
        if service.get("id"):
            command = ["systemctl"]
            if service.get("scope") == "user":
                command.append("--user")
            command.extend(
                [
                    "show",
                    service["id"],
                    "--property=LoadState,ActiveState,SubState,ControlGroup,FragmentPath",
                ]
            )
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            values = dict(
                line.split("=", 1)
                for line in completed.stdout.splitlines()
                if "=" in line
            )
            self.assertEqual(service["loadState"], values["LoadState"])
            self.assertEqual(service["activeState"], values["ActiveState"])
            self.assertEqual(service["subState"], values["SubState"])
            self.assertEqual(service["controlGroup"], values["ControlGroup"])
            self.assertEqual(service["fragmentPath"], values["FragmentPath"])

        for node in context["cause"]["nodes"]:
            pid = int(node.get("pid", 0))
            if pid <= 0:
                self.assertEqual(node["kind"], "service")
                continue
            stat = proc_stat(pid)
            self.assertEqual(node["title"], stat["name"])
            self.assertIn(f"parent PID {stat['ppid']}", node["proof"])

    def _assert_explanations(self, snapshot: dict[str, object]) -> None:
        triggers = {
            "public-listener": any(
                row["externallyReachable"] for row in snapshot["connections"]
            ),
            "deleted-open-files": any(row["deleted"] for row in snapshot["files"]),
            "file-locks": bool(snapshot["locks"]),
            "effective-capabilities": bool(snapshot["security"]["capabilities"]),
            "privileged-container": bool(
                snapshot["context"].get("container", {}).get("privileged")
            ),
            "journal-errors": any(
                str(row.get("priority", "9")).isdigit()
                and int(row.get("priority", 9)) <= 3
                for row in snapshot["logs"]
            ),
            "limited-coverage": bool(snapshot["coverage"]["limited"]),
        }
        privacy = [
            row
            for row in snapshot["devices"]["pipewire"]
            if row["active"] and row["kind"] in {"microphone", "camera", "screen"}
        ]
        for row in snapshot["explanations"]:
            identifier = row["id"]
            if identifier.startswith("privacy-"):
                self.assertTrue(privacy)
            elif identifier == "no-supported-finding":
                self.assertFalse(any(triggers.values()) or privacy)
            else:
                self.assertTrue(triggers[identifier], identifier)
                self.assertTrue(row["evidence"], identifier)
            self.assertTrue(row["nextStep"])

    def _assert_every_drilldown(self, snapshot: dict[str, object]) -> None:
        rendered = rendered_details(snapshot)
        self.assertEqual(
            rendered["counts"],
            {name: len(rows) for name, rows in rendered["rows"].items()},
        )
        devices = snapshot["devices"]
        availability = devices["availability"]
        device_limits = sum(
            availability.get(name) in {False, "unavailable", "partial"}
            for name in ("pipewire", "gpu", "inhibitors")
        )
        security = snapshot["security"]
        context = snapshot["context"]
        service = context.get("service", {})
        container = context.get("container", {})
        runtime_count = (
            5
            + bool(security.get("apparmor"))
            + (security.get("oomScore") is not None)
            + bool(context.get("package", {}).get("name"))
            + bool(context.get("git", {}).get("root"))
            + len(security["namespaces"])
            + len(security["limits"])
            + len(security["libraries"])
            + len(snapshot["logs"])
        )
        if service.get("id"):
            runtime_count += (
                2
                + bool(service.get("fragmentPath"))
                + len(service.get("triggeredBy", []))
            )
        if container.get("id"):
            runtime_count += (
                2
                + len(container.get("ports", []))
                + len(container.get("mounts", []))
                + len(container.get("networks", []))
            )
        expected = {
            "processes": len(snapshot["processes"]),
            "connections": len(snapshot["connections"]),
            "files": len(snapshot["files"]) + len(snapshot["locks"]),
            "devices": len(devices["pipewire"])
            + len(devices["gpu"])
            + len(devices["inhibitors"])
            + device_limits,
            "runtime": runtime_count,
            "cause": len(context["cause"]["nodes"]),
            "explanations": len(snapshot["explanations"])
            + len(snapshot["timeline"]),
            "coverage": len(snapshot["coverage"]["available"])
            + len(snapshot["coverage"]["limited"]),
            "alternatives": len(snapshot["target"]["alternatives"]),
        }
        self.assertEqual(rendered["counts"], expected)

        rows = rendered["rows"]
        self.assertEqual(
            {int(row["pid"]) for row in rows["processes"]},
            {int(row["pid"]) for row in snapshot["processes"]},
        )
        self.assertEqual(
            {row["title"] for row in rows["coverage"]},
            set(snapshot["coverage"]["available"])
            | set(snapshot["coverage"]["limited"]),
        )
        self.assertEqual(
            {int(row["pid"]) for row in rows["alternatives"]},
            {int(row["pid"]) for row in snapshot["target"]["alternatives"]},
        )
        if rows["runtime"]:
            self.assertTrue(
                any(
                    row["title"] == "Executable"
                    and row["subtitle"] == context["executable"]
                    for row in rows["runtime"]
                )
            )
        for node, rendered_row in zip(
            context["cause"]["nodes"], rows["cause"], strict=True
        ):
            self.assertEqual(rendered_row["subtitle"], node["proof"])


if __name__ == "__main__":
    unittest.main()
