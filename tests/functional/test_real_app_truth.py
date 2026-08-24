from __future__ import annotations

import json
import math
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest

from live_backend import LiveBackend
from machine_truth import (
    command_json,
    descriptor_info,
    descriptor_targets,
    display_bytes,
    display_duration,
    display_percent,
    display_rate,
    docker_inspect,
    expected_detail_counts,
    hyprland_clients,
    proc_cgroup_paths,
    proc_io,
    proc_security,
    proc_stat,
    proc_status,
    raw_drm_clients,
    raw_drm_details,
    raw_locks,
    raw_journal_entries,
    raw_pipewire_kind,
    raw_pipewire_streams,
    raw_socket_inventory,
    rendered_details,
    system_cpu_ticks,
    systemd_show,
)
from xray.evidence.redaction import redact_command, redact_text


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
        for label, predicate in (
            ("Zed", lambda row: "zed" in str(row.get("class", "")).lower()),
            ("Discord", lambda row: "discord" in str(row.get("class", "")).lower()),
        ):
            if window := next((row for row in clients if predicate(row)), None):
                cls.windows[label] = window
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
        baseline_before = self._live_domains(initial_pids)
        baseline_response = self.backend.request("refresh")
        self.assertTrue(baseline_response["ok"], baseline_response)
        baseline_pids = [
            int(row["pid"]) for row in baseline_response["data"]["processes"]
        ]
        self.truth_before = self._live_domains(baseline_pids)
        time.sleep(0.25)
        current_before = self._live_domains(baseline_pids)
        windows_before = hyprland_clients()
        refreshed = self.backend.request("refresh")
        self.assertTrue(refreshed["ok"], refreshed)
        windows_after = hyprland_clients()
        refreshed_pids = [int(row["pid"]) for row in refreshed["data"]["processes"]]
        self.truth_after = self._live_domains(refreshed_pids)
        self.rate_boundaries = (
            baseline_before,
            self.truth_before,
            current_before,
            self.truth_after,
        )
        self.window_boundaries = tuple(
            row
            for rows in (windows_before, windows_after)
            for row in rows
            if str(row.get("address", "")) == str(address)
        )
        return refreshed["data"]

    @staticmethod
    def _live_domains(pids: list[int]) -> dict[str, object]:
        sampled_at = time.monotonic()
        total_cpu_ticks = system_cpu_ticks()
        processes: dict[int, dict[str, object]] = {}
        files: set[tuple[int, int, str]] = set()
        file_details: dict[tuple[int, int, str], dict[str, object]] = {}
        descriptors: dict[int, dict[int, str]] = {}
        for pid in pids:
            try:
                raw_command = Path(f"/proc/{pid}/cmdline").read_bytes()
                processes[pid] = {
                    "stat": proc_stat(pid),
                    "status": proc_status(pid),
                    "io": proc_io(pid),
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
            descriptors[pid] = descriptor_targets(pid)
            for fd, target in descriptors[pid].items():
                identity = (pid, fd, target)
                files.add(identity)
                if info := descriptor_info(pid, fd):
                    file_details[identity] = info
        pid_set = set(pids)
        gpu_details = raw_drm_details(pids, descriptors)
        return {
            "sampledAt": sampled_at,
            "systemUptime": float(Path("/proc/uptime").read_text().split()[0]),
            "totalCpuTicks": total_cpu_ticks,
            "processes": processes,
            "connections": raw_socket_inventory(pids, descriptors),
            "files": files,
            "fileDetails": file_details,
            "locks": {row for row in raw_locks() if row[3] in pid_set},
            "pipewire": {
                key: value
                for key, value in raw_pipewire_streams().items()
                if key[1] in pid_set
            },
            "gpu": set(gpu_details),
            "gpuDetails": gpu_details,
        }

    def test_every_card_and_drilldown_matches_diverse_live_applications(self) -> None:
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

    def test_live_systemd_target_matches_primary_tool(self) -> None:
        unit = "pipewire.service"
        expected_service = systemd_show(unit, "user")
        self.assertGreater(expected_service["mainPid"], 0)
        response = self.backend.request("inspect", query=f"service:user:{unit}")
        self.assertTrue(response["ok"], response)
        service_snapshot = response["data"]
        self.assertEqual(service_snapshot["target"]["label"], unit)
        self.assertEqual(service_snapshot["context"]["service"], expected_service)
        service_processes = service_snapshot["processes"]
        raw_logs = raw_journal_entries(
            int(expected_service["mainPid"]),
            int(service_processes[0]["startTime"]),
            [int(row["pid"]) for row in service_processes],
            unit,
            "user",
        )
        expected_logs = [
            {**row, "message": redact_text(row["message"])[:4000]} for row in raw_logs
        ]
        observed_logs = service_snapshot["logs"]
        if observed_logs:
            starts = [
                index
                for index in range(len(expected_logs) - len(observed_logs) + 1)
                if expected_logs[index : index + len(observed_logs)] == observed_logs
            ]
            self.assertTrue(starts, "displayed journal rows differ from journalctl")
            skipped_prefix = expected_logs[: starts[0]]
            uptime = float(Path("/proc/uptime").read_text().split()[0])
            process_started = (
                time.time()
                - uptime
                + int(service_processes[0]["startTime"]) / os.sysconf("SC_CLK_TCK")
            )
            self.assertTrue(
                all(
                    abs(int(row["timestamp"]) / 1_000_000 - process_started) <= 0.1
                    for row in skipped_prefix
                ),
                "journal entries after process start were omitted",
            )
        else:
            self.assertFalse(expected_logs)
        rendered_service = rendered_details(service_snapshot)
        runtime_rows = rendered_service["rows"]["runtime"]
        self.assertTrue(
            any(
                row["title"] == "Activated by" and row["subtitle"] == "pipewire.socket"
                for row in runtime_rows
            )
        )
        raw_cgroups = proc_cgroup_paths(int(expected_service["mainPid"]))
        self.assertEqual(service_snapshot["context"]["launch"]["paths"], raw_cgroups)
        control_group_card = next(
            row
            for row in rendered_service["cards"]["runtime"]
            if row["title"] == "Control group"
        )
        self.assertEqual(control_group_card["subtitle"], ", ".join(raw_cgroups))
        self._assert_every_drilldown(service_snapshot, rendered_service)

    def test_live_container_target_matches_primary_tool(self) -> None:
        if not shutil.which("docker"):
            self.skipTest("Docker is not installed")
        listed = subprocess.run(
            ["docker", "ps", "--quiet", "--no-trunc"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
            check=False,
        )
        if listed.returncode != 0 or not listed.stdout.splitlines():
            self.skipTest("No running Docker container is available")
        identifier = listed.stdout.splitlines()[0]
        raw = docker_inspect(identifier)
        response = self.backend.request(
            "inspect", query=f"container:docker:{identifier}"
        )
        self.assertTrue(response["ok"], response)
        container_snapshot = response["data"]
        container = container_snapshot["context"]["container"]
        config = raw.get("Config", {})
        state = raw.get("State", {})
        host = raw.get("HostConfig", {})
        network = raw.get("NetworkSettings", {})
        labels = config.get("Labels") or {}
        self.assertEqual(container_snapshot["target"]["rootPid"], state["Pid"])
        self.assertEqual(container_snapshot["target"]["label"], raw["Name"].lstrip("/"))
        self.assertEqual(container["id"], raw["Id"])
        self.assertEqual(container["shortId"], raw["Id"][:12])
        self.assertEqual(container["name"], raw["Name"].lstrip("/"))
        self.assertEqual(container["image"], config.get("Image", ""))
        self.assertEqual(container["pid"], state.get("Pid", 0))
        self.assertEqual(container["state"], state.get("Status", ""))
        self.assertEqual(container["running"], state.get("Running", False))
        self.assertEqual(container["created"], raw.get("Created", ""))
        self.assertEqual(container["command"], redact_command(config.get("Cmd", [])))
        self.assertEqual(
            container["entrypoint"], redact_command(config.get("Entrypoint", []))
        )
        self.assertEqual(
            container["restartPolicy"],
            (host.get("RestartPolicy") or {}).get("Name", ""),
        )
        self.assertEqual(container["privileged"], host.get("Privileged", False))
        self.assertEqual(
            container["composeProject"],
            labels.get("com.docker.compose.project", ""),
        )
        self.assertEqual(
            container["composeService"],
            labels.get("com.docker.compose.service", ""),
        )
        self.assertEqual(
            container["composeWorkingDirectory"],
            labels.get("com.docker.compose.project.working_dir", ""),
        )
        expected_mounts = {
            (
                str(row.get("Type", "")),
                str(row.get("Source", "")),
                str(row.get("Destination", "")),
                not bool(row.get("RW", True)),
            )
            for row in raw.get("Mounts", [])
        }
        self.assertEqual(
            {
                (row["type"], row["source"], row["destination"], row["readOnly"])
                for row in container["mounts"]
            },
            expected_mounts,
        )
        expected_networks = {
            (
                str(name),
                str(values.get("IPAddress", "")),
                str(values.get("Gateway", "")),
            )
            for name, values in (network.get("Networks") or {}).items()
        }
        self.assertEqual(
            {
                (row["name"], row["address"], row["gateway"])
                for row in container["networks"]
            },
            expected_networks,
        )
        expected_ports = {
            (
                endpoint.partition("/")[0],
                endpoint.partition("/")[2],
                str(binding.get("HostIp", "")),
                str(binding.get("HostPort", "")),
            )
            for endpoint, bindings in (network.get("Ports") or {}).items()
            for binding in bindings or []
        }
        self.assertEqual(
            {
                (
                    row["containerPort"],
                    row["protocol"],
                    row["hostAddress"],
                    row["hostPort"],
                )
                for row in container["ports"]
            },
            expected_ports,
        )
        rendered_container = rendered_details(container_snapshot)
        container_titles = {
            row["title"] for row in rendered_container["rows"]["runtime"]
        }
        if container.get("entrypoint") or container.get("command"):
            self.assertIn("Container command", container_titles)
        if container.get("composeProject") or container.get("composeService"):
            self.assertIn("Compose workload", container_titles)
        if container.get("composeWorkingDirectory"):
            self.assertIn("Compose working directory", container_titles)
        self._assert_every_drilldown(container_snapshot, rendered_container)

    def test_target_catalog_counts_and_rows_match_live_system_tools(self) -> None:
        before_pids = self._same_user_pids()
        before_windows = hyprland_clients()
        before_pipewire = raw_pipewire_streams()
        before_gpu = raw_drm_clients(before_pids)
        before_ports = raw_socket_inventory(before_pids)

        response = self.backend.request("catalog")
        self.assertTrue(response["ok"], response)
        catalog = response["data"]

        after_pids = self._same_user_pids()
        after_windows = hyprland_clients()
        after_pipewire = raw_pipewire_streams()
        after_gpu = raw_drm_clients(after_pids)
        after_ports = raw_socket_inventory(after_pids)

        self.assertEqual(
            len(catalog["quickTargets"]),
            4,
            "all four fixed quick inspections must show",
        )
        self.assertEqual(
            {row["query"] for row in catalog["quickTargets"]},
            {"microphone", "camera", "gpu", "audio"},
        )
        displayed_target_count = sum(
            len(catalog[name])
            for name in (
                "windows",
                "processes",
                "devices",
                "gpu",
                "ports",
                "services",
                "containers",
            )
        )
        self.assertGreater(displayed_target_count, 0)

        window_candidates = {
            (str(row.get("address", "")), int(row.get("pid", 0))): row
            for row in (*before_windows, *after_windows)
        }
        for row in catalog["windows"]:
            raw = window_candidates[(str(row["address"]), int(row["pid"]))]
            self.assertEqual(
                row["class"], str(raw.get("class", raw.get("initialClass", "")))
            )
            self.assertEqual(
                row["title"], str(raw.get("title", raw.get("initialTitle", "")))
            )
            self.assertEqual(row["workspace"], raw.get("workspace", {}))
            self.assertEqual(row["query"], f"window:{row['address']}")

        stable_pids = set(before_pids) & set(after_pids)
        observed_pids = {int(row["pid"]) for row in catalog["processes"]}
        process_limit = any(
            "Process search is limited" in row for row in catalog["limited"]
        )
        if not process_limit:
            self.assertTrue(stable_pids <= observed_pids)
        for row in catalog["processes"]:
            pid = int(row["pid"])
            try:
                name = str(proc_stat(pid)["name"])
            except OSError:
                name = ""
            if name:
                self.assertEqual(row["name"], name)
            self.assertEqual(row["query"], f"pid:{pid}")

        for row in catalog["devices"]:
            key = (int(row["id"]), int(row["pid"]))
            candidates = [
                source[key]
                for source in (before_pipewire, after_pipewire)
                if key in source
            ]
            self.assertTrue(candidates)
            for field in (
                "name",
                "application",
                "mediaClass",
                "role",
                "state",
                "source",
                "sourceIds",
                "active",
            ):
                self.assertIn(row[field], [raw[field] for raw in candidates])
            self.assertIn(row["kind"], [raw_pipewire_kind(raw) for raw in candidates])
            self.assertTrue(row["active"])
            self.assertEqual(row["query"], f"pid:{row['pid']}")

        gpu_candidates = before_gpu | after_gpu
        for row in catalog["gpu"]:
            identity = (int(row["pid"]), str(row["device"]), str(row["clientId"]))
            self.assertIn(identity, gpu_candidates)
            self.assertEqual(row["query"], f"pid:{row['pid']}")

        port_candidates = before_ports | after_ports
        for row in catalog["ports"]:
            identity = (
                str(row["networkNamespace"]),
                int(row["inode"]),
                str(row["protocol"]),
                str(row["localAddress"]),
                int(row["localPort"]),
                str(row["remoteAddress"]),
                int(row["remotePort"]),
                str(row["state"]),
            )
            self.assertIn(identity, port_candidates)
            self.assertTrue(row["listening"])
            self.assertEqual(set(row["pids"]), port_candidates[identity])
            self.assertEqual(row["query"], f":{row['localPort']}")

        service_truth: dict[tuple[str, str], dict[str, object]] = {}
        for scope in ("user", "system"):
            argv = ["systemctl"]
            if scope == "user":
                argv.append("--user")
            argv.extend(
                [
                    "list-units",
                    "--type=service",
                    "--type=scope",
                    "--state=running",
                    "--no-pager",
                    "--output=json",
                ]
            )
            payload = command_json(argv)
            self.assertIsInstance(payload, list)
            for raw in payload:
                self.assertIsInstance(raw, dict)
                service_truth[(scope, str(raw["unit"]))] = raw
        for row in catalog["services"]:
            raw = service_truth[(str(row["scope"]), str(row["id"]))]
            self.assertEqual(row["description"], raw.get("description") or raw["unit"])
            self.assertEqual(row["loadState"], raw.get("load", ""))
            self.assertEqual(row["activeState"], raw.get("active", ""))
            self.assertEqual(row["subState"], raw.get("sub", ""))
            self.assertEqual(row["query"], f"service:{row['scope']}:{row['id']}")

        container_truth: dict[tuple[str, str], dict[str, object]] = {}
        runtimes = {str(row["runtime"]) for row in catalog["containers"]}
        for runtime in runtimes:
            ids = [
                str(row["id"])
                for row in catalog["containers"]
                if str(row["runtime"]) == runtime
            ]
            payload = command_json([runtime, "inspect", "--", *ids])
            self.assertIsInstance(payload, list)
            for raw in payload:
                self.assertIsInstance(raw, dict)
                container_truth[(runtime, str(raw["Id"]))] = raw
        for row in catalog["containers"]:
            runtime = str(row["runtime"])
            raw = container_truth[(runtime, str(row["id"]))]
            config = raw.get("Config", {})
            labels = config.get("Labels") or {}
            self.assertEqual(row["name"], str(raw.get("Name", "")).lstrip("/"))
            self.assertEqual(row["image"], config.get("Image", ""))
            self.assertEqual(
                row["composeProject"], labels.get("com.docker.compose.project", "")
            )
            self.assertEqual(
                row["composeService"], labels.get("com.docker.compose.service", "")
            )
            self.assertEqual(row["query"], f"container:{runtime}:{row['id']}")

    @staticmethod
    def _same_user_pids() -> list[int]:
        result = []
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            try:
                if int(proc_status(int(path.name))["Uid"].split()[0]) == os.getuid():
                    result.append(int(path.name))
            except (KeyError, OSError, ValueError):
                continue
        return sorted(result)

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
        window_candidates = self.window_boundaries or (expected_window,)
        if "ghostty" in str(window["class"]).lower():
            self.assertIn(
                str(window["title"]).partition(" ")[2],
                {
                    str(candidate["title"]).partition(" ")[2]
                    for candidate in window_candidates
                },
            )
        else:
            self.assertIn(
                window["title"], {candidate["title"] for candidate in window_candidates}
            )
        self.assertIn(
            window["workspace"],
            [candidate["workspace"] for candidate in window_candidates],
        )
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
                for source in self.rate_boundaries
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
            samples = [source["processes"].get(pid) for source in self.rate_boundaries]
            before = samples[1]
            after = samples[3]
            if (
                all(samples)
                and before
                and after
                and before["stat"]["startTime"] == after["stat"]["startTime"]
                and row["cpuPercent"] is not None
            ):
                baseline_before, baseline_after, current_before, current_after = (
                    self.rate_boundaries
                )
                minimum_process_delta = max(
                    0,
                    int(current_before["processes"][pid]["stat"]["cpuTicks"])
                    - int(baseline_after["processes"][pid]["stat"]["cpuTicks"]),
                )
                maximum_process_delta = max(
                    0,
                    int(current_after["processes"][pid]["stat"]["cpuTicks"])
                    - int(baseline_before["processes"][pid]["stat"]["cpuTicks"]),
                )
                minimum_total_delta = max(
                    1,
                    int(current_before["totalCpuTicks"])
                    - int(baseline_after["totalCpuTicks"]),
                )
                maximum_total_delta = max(
                    1,
                    int(current_after["totalCpuTicks"])
                    - int(baseline_before["totalCpuTicks"]),
                )
                minimum_cpu = minimum_process_delta / maximum_total_delta * 100
                maximum_cpu = maximum_process_delta / minimum_total_delta * 100
                self.assertGreaterEqual(float(row["cpuPercent"]), minimum_cpu - 0.11)
                self.assertLessEqual(
                    float(row["cpuPercent"]),
                    maximum_cpu + 0.11,
                    f"PID {pid} CPU is outside its /proc sampling bounds",
                )
                for field, counter in (
                    ("readBytesPerSecond", "read_bytes"),
                    ("writeBytesPerSecond", "write_bytes"),
                ):
                    if row[field] is None or any(
                        sample["io"] is None for sample in samples
                    ):
                        continue
                    minimum_counter_delta = max(
                        0,
                        int(samples[2]["io"][counter]) - int(samples[1]["io"][counter]),
                    )
                    maximum_counter_delta = max(
                        0,
                        int(samples[3]["io"][counter]) - int(samples[0]["io"][counter]),
                    )
                    minimum_elapsed = max(
                        0.001,
                        float(self.rate_boundaries[2]["sampledAt"])
                        - float(self.rate_boundaries[1]["sampledAt"]),
                    )
                    maximum_elapsed = max(
                        minimum_elapsed,
                        float(self.rate_boundaries[3]["sampledAt"])
                        - float(self.rate_boundaries[0]["sampledAt"]),
                    )
                    minimum_rate = minimum_counter_delta / maximum_elapsed
                    maximum_rate = maximum_counter_delta / minimum_elapsed
                    self.assertGreaterEqual(float(row[field]), minimum_rate - 1)
                    self.assertLessEqual(
                        float(row[field]),
                        maximum_rate + 1,
                        f"PID {pid} {field} is outside its /proc sampling bounds",
                    )
        self.assertGreaterEqual(verified, max(1, int(len(rows) * 0.9)))
        if all(row["cpuPercent"] is not None for row in rows):
            self.assertLessEqual(
                abs(
                    float(metrics["cpuPercent"])
                    - sum(float(row["cpuPercent"]) for row in rows)
                ),
                max(0.2, len(rows) * 0.05),
            )
        if metrics["ioAvailable"]:
            for metric, field in (
                ("readBytesPerSecond", "readBytesPerSecond"),
                ("writeBytesPerSecond", "writeBytesPerSecond"),
            ):
                self.assertLessEqual(
                    abs(
                        int(metrics[metric]) - sum(int(row[field] or 0) for row in rows)
                    ),
                    len(rows),
                )
        clock_ticks = os.sysconf("SC_CLK_TCK")
        uptime_bounds = [
            max(
                0,
                round(
                    float(source["systemUptime"])
                    - int(rows[0]["startTime"]) / clock_ticks
                ),
            )
            for source in self.rate_boundaries[2:]
        ]
        self.assertGreaterEqual(int(metrics["uptimeSeconds"]), min(uptime_bounds))
        self.assertLessEqual(int(metrics["uptimeSeconds"]), max(uptime_bounds))
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
        before_snapshot, after_snapshot = self.rate_boundaries[2:]
        bracketed = before_snapshot["files"] | after_snapshot["files"]
        checked = 0
        for row in snapshot["files"]:
            pid = int(row["pid"])
            fd = int(row["fd"])
            target = str(row["target"])
            if (pid, fd, target) not in bracketed:
                continue
            checked += 1
            candidates = [
                source["fileDetails"][(pid, fd, target)]
                for source in (before_snapshot, after_snapshot)
                if (pid, fd, target) in source["fileDetails"]
            ]
            if candidates and "mode" in row:
                for field in ("position", "flags", "mode", "mountId"):
                    self.assertIn(
                        row[field], [candidate[field] for candidate in candidates]
                    )
            self.assertEqual(row["deleted"], target.endswith(" (deleted)"))
        self.assertGreaterEqual(checked, max(1, int(len(snapshot["files"]) * 0.8)))

        observed_files = {
            (int(row["pid"]), int(row["fd"]), str(row["target"]))
            for row in snapshot["files"]
        }
        stable_files = {
            row
            for row in before_snapshot["files"] & after_snapshot["files"]
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
            candidates = [
                source["pipewire"][key]
                for source in (self.truth_before, self.truth_after)
                if key in source["pipewire"]
            ]
            self.assertTrue(candidates)
            raw = candidates[-1]
            self.assertTrue(
                str(raw["props"].get("media.class", "")).startswith("Stream/")
            )
            for field in (
                "mediaClass",
                "role",
                "name",
                "application",
                "state",
                "active",
                "sourceIds",
                "source",
            ):
                self.assertIn(
                    row[field], [candidate[field] for candidate in candidates]
                )
            self.assertIn(
                row["kind"], [raw_pipewire_kind(candidate) for candidate in candidates]
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
            candidates = [
                source["gpuDetails"][key]
                for source in (self.truth_before, self.truth_after)
                if key in source["gpuDetails"]
            ]
            self.assertTrue(candidates)
            self.assertIn(
                row["capacity"], [candidate["capacity"] for candidate in candidates]
            )
            self.assertIn(
                row["memoryKind"], [candidate["memoryKind"] for candidate in candidates]
            )
            self.assertEqual(
                row["memoryBytes"],
                sum(int(amount) for amount in row["memory"].values()),
            )
            for engine, counter in row["engines"].items():
                values = [
                    int(candidate["engines"][engine])
                    for candidate in candidates
                    if engine in candidate["engines"]
                ]
                self.assertTrue(values)
                self.assertGreaterEqual(int(counter), min(values))
                self.assertLessEqual(int(counter), max(values))
            samples = [source["gpuDetails"].get(key) for source in self.rate_boundaries]
            if value is not None and all(samples):
                minimum_elapsed = max(
                    1.0,
                    (
                        float(self.rate_boundaries[2]["sampledAt"])
                        - float(self.rate_boundaries[1]["sampledAt"])
                    )
                    * 1_000_000_000,
                )
                maximum_elapsed = max(
                    minimum_elapsed,
                    (
                        float(self.rate_boundaries[3]["sampledAt"])
                        - float(self.rate_boundaries[0]["sampledAt"])
                    )
                    * 1_000_000_000,
                )
                minimum_delta = sum(
                    max(
                        0,
                        int(samples[2]["engines"].get(engine, 0))
                        - int(samples[1]["engines"].get(engine, 0)),
                    )
                    for engine in row["engines"]
                )
                maximum_delta = sum(
                    max(
                        0,
                        int(samples[3]["engines"].get(engine, 0))
                        - int(samples[0]["engines"].get(engine, 0)),
                    )
                    for engine in row["engines"]
                )
                capacity = sum(
                    max(1, int(row.get("capacity", {}).get(engine, 1)))
                    for engine in row["engines"]
                )
                minimum_utilization = minimum_delta / (maximum_elapsed * capacity) * 100
                maximum_utilization = min(
                    100.0, maximum_delta / (minimum_elapsed * capacity) * 100
                )
                self.assertGreaterEqual(float(value), minimum_utilization - 0.11)
                self.assertLessEqual(float(value), maximum_utilization + 0.11)
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
            raw_rows = command_json(["systemd-inhibit", "--list", "--json=short"])
            self.assertIsInstance(raw_rows, list)
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
        self._assert_aggregate_gpu_rate(snapshot)

    def _assert_aggregate_gpu_rate(self, snapshot: dict[str, object]) -> None:
        value = snapshot["metrics"].get("gpuPercent")
        if value is None:
            return
        keys = [
            (int(row["pid"]), str(row["device"]), str(row["clientId"]))
            for row in snapshot["devices"]["gpu"]
        ]
        if not keys or any(
            key not in source["gpuDetails"]
            for source in self.rate_boundaries
            for key in keys
        ):
            return
        minimum_elapsed = max(
            1.0,
            (
                float(self.rate_boundaries[2]["sampledAt"])
                - float(self.rate_boundaries[1]["sampledAt"])
            )
            * 1_000_000_000,
        )
        maximum_elapsed = max(
            minimum_elapsed,
            (
                float(self.rate_boundaries[3]["sampledAt"])
                - float(self.rate_boundaries[0]["sampledAt"])
            )
            * 1_000_000_000,
        )
        minimum_delta = 0
        maximum_delta = 0
        capacities: dict[tuple[str, str], int] = {}
        for row, key in zip(snapshot["devices"]["gpu"], keys, strict=True):
            samples = [source["gpuDetails"][key] for source in self.rate_boundaries]
            for engine in row["engines"]:
                minimum_delta += max(
                    0,
                    int(samples[2]["engines"].get(engine, 0))
                    - int(samples[1]["engines"].get(engine, 0)),
                )
                maximum_delta += max(
                    0,
                    int(samples[3]["engines"].get(engine, 0))
                    - int(samples[0]["engines"].get(engine, 0)),
                )
                capacity_key = (str(row["device"]), str(engine))
                capacities[capacity_key] = max(
                    capacities.get(capacity_key, 0),
                    max(1, int(row.get("capacity", {}).get(engine, 1))),
                )
        capacity = sum(capacities.values())
        if not capacity:
            return
        minimum_utilization = minimum_delta / (maximum_elapsed * capacity) * 100
        maximum_utilization = min(
            100.0, maximum_delta / (minimum_elapsed * capacity) * 100
        )
        self.assertGreaterEqual(float(value), minimum_utilization - 0.11)
        self.assertLessEqual(float(value), maximum_utilization + 0.11)

    def _assert_runtime_and_cause(self, snapshot: dict[str, object]) -> None:
        root_pid = int(snapshot["target"]["rootPid"])
        context = snapshot["context"]
        security = snapshot["security"]
        raw_security = proc_security(root_pid)
        for key in (
            "uid",
            "gid",
            "groups",
            "noNewPrivileges",
            "seccomp",
            "capabilities",
            "capabilitiesKnown",
            "apparmor",
            "oomScore",
            "oomAdjustment",
            "namespaces",
            "limits",
            "libraries",
        ):
            with self.subTest(runtime_field=key):
                self.assertEqual(security[key], raw_security[key])

        launch = context.get("launch", {})
        raw_cgroups = proc_cgroup_paths(root_pid)
        self.assertEqual(launch.get("paths", []), raw_cgroups)

        package = context.get("package", {})
        if package.get("name"):
            owner = subprocess.run(
                ["pacman", "-Qo", "--quiet", context["executable"]],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
                check=False,
            )
            self.assertEqual(owner.returncode, 0, owner.stderr)
            self.assertEqual(package["name"], owner.stdout.strip())
            installed = subprocess.run(
                ["pacman", "-Q", package["name"]],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
                check=False,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            self.assertEqual(
                installed.stdout.strip(),
                f"{package['name']} {package['version']}",
            )

        service = context.get("service", {})
        if service.get("id"):
            self.assertEqual(
                service,
                systemd_show(str(service["id"]), str(service["scope"])),
            )

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

    def _assert_every_drilldown(
        self,
        snapshot: dict[str, object],
        rendered: dict[str, object] | None = None,
    ) -> None:
        rendered = rendered or rendered_details(snapshot)
        self.assertEqual(
            rendered["counts"],
            {name: len(rows) for name, rows in rendered["rows"].items()},
        )
        security = snapshot["security"]
        context = snapshot["context"]
        expected = expected_detail_counts(snapshot)
        runtime_count = expected["runtime"]
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
                    and row["subtitle"] == (context["executable"] or "Unavailable")
                    for row in rows["runtime"]
                )
            )
        for node, rendered_row in zip(
            context["cause"]["nodes"], rows["cause"], strict=True
        ):
            self.assertEqual(rendered_row["subtitle"], node["proof"])

        process_summary = {
            "processes": len(snapshot["processes"]),
            "threads": sum(int(row["threads"]) for row in snapshot["processes"]),
            "memoryBytes": sum(
                int(row["memoryBytes"]) for row in snapshot["processes"]
            ),
        }
        self.assertEqual(rendered["cards"]["processSummary"], process_summary)
        self.assertEqual(
            rendered["details"]["processes"],
            f"{process_summary['processes']} processes  ·  "
            f"{process_summary['threads']} threads  ·  "
            f"{display_bytes(process_summary['memoryBytes'])} resident",
        )
        expected_details = {
            "connections": f"{len(snapshot['connections'])} endpoints",
            "files": (
                f"{len(snapshot['files'])} descriptors  ·  "
                f"{len(snapshot['locks'])} locks"
            ),
            "runtime": f"{runtime_count} evidence records",
            "cause": f"{len(context['cause']['nodes'])} launch steps",
            "explanations": (
                f"{len(snapshot['explanations'])} findings  ·  "
                f"{len(snapshot['timeline'])} changes"
            ),
            "coverage": (
                f"{len(snapshot['coverage']['available']) + len(snapshot['coverage']['limited'])} "
                "evidence sources"
            ),
            "alternatives": (
                f"{len(snapshot['target']['alternatives'])} process matches"
            ),
        }
        for domain, detail in expected_details.items():
            self.assertEqual(rendered["details"][domain], detail)

        for domain, sections in rendered["sections"].items():
            if sections:
                self.assertEqual(
                    sum(int(section["sourceCount"]) for section in sections),
                    expected[domain],
                )

        summaries = {
            domain: {row["label"]: row["value"] for row in values}
            for domain, values in rendered["summaries"].items()
        }
        connections = snapshot["connections"]
        self.assertEqual(
            summaries["connections"],
            {
                "LISTENERS": str(sum(row["listening"] is True for row in connections)),
                "REMOTE": str(
                    sum(int(row.get("remotePort", 0) or 0) > 0 for row in connections)
                ),
                "NAMESPACES": str(
                    len(
                        {
                            str(row["networkNamespace"])
                            for row in connections
                            if row.get("networkNamespace")
                        }
                    )
                ),
                "EXPOSED": str(
                    sum(row["externallyReachable"] is True for row in connections)
                ),
            },
        )
        file_groups = {
            (
                self._file_section(row),
                str(row["target"]),
                str(row.get("kind", "file")),
                str(row.get("mode", "unknown")),
                row["deleted"] is True,
            )
            for row in snapshot["files"]
        }
        self.assertEqual(
            summaries["files"],
            {
                "DESCRIPTORS": str(len(snapshot["files"])),
                "RESOURCES": str(len(file_groups)),
                "LOCKS": str(len(snapshot["locks"])),
                "DELETED": str(
                    sum(row["deleted"] is True for row in snapshot["files"])
                ),
            },
        )
        self.assertEqual(
            summaries["runtime"],
            {
                "SECCOMP": str(security.get("seccomp") or "unknown").upper(),
                "NO NEW PRIVS": (
                    "ON"
                    if security.get("noNewPrivileges") is True
                    else "OFF"
                    if security.get("noNewPrivileges") is False
                    else "UNKNOWN"
                ),
                "NAMESPACES": str(len(security.get("namespaces", {}))),
                "EFFECTIVE CAPS": (
                    str(len(security.get("capabilities", [])))
                    if security.get("capabilitiesKnown") is True
                    else "UNKNOWN"
                ),
            },
        )
        findings = snapshot["explanations"]
        self.assertEqual(
            summaries["explanations"],
            {
                "FINDINGS": str(len(findings)),
                "ATTENTION": str(
                    sum(row.get("tone") == "attention" for row in findings)
                ),
                "EVIDENCE": str(sum(len(row.get("evidence", [])) for row in findings)),
                "CHANGES": str(len(snapshot["timeline"])),
            },
        )
        self.assertEqual(
            summaries["coverage"],
            {
                "AVAILABLE": str(len(snapshot["coverage"]["available"])),
                "LIMITED": str(len(snapshot["coverage"]["limited"])),
            },
        )
        self._assert_identity_and_metric_cards(snapshot, rendered["cards"])
        self._assert_device_summary(snapshot, rendered["cards"]["devices"])

    @staticmethod
    def _file_section(row: dict[str, object]) -> str:
        target = str(row.get("target", ""))
        if row.get("deleted") is True:
            return "attention"
        if target.startswith("anon_inode:"):
            return "events"
        if target.startswith("socket:["):
            return "sockets"
        if target.startswith("pipe:["):
            return "pipes"
        if target.startswith("/dev/"):
            return "devices"
        if target.startswith("memfd:") or target.startswith("/dev/shm/"):
            return "memory"
        return "files" if target.startswith("/") else "other"

    def _assert_identity_and_metric_cards(
        self, snapshot: dict[str, object], cards: dict[str, object]
    ) -> None:
        owner_pid = int(snapshot["target"]["ownerPid"])
        selected = next(
            (row for row in snapshot["processes"] if int(row["pid"]) == owner_pid),
            {},
        )
        selected_card = cards["selectedProcess"]
        self.assertEqual(selected_card["pid"], owner_pid)
        self.assertEqual(selected_card["user"], selected.get("user", "unknown"))
        state_labels = {
            "R": "running",
            "S": "sleeping",
            "D": "disk wait",
            "T": "stopped",
            "t": "tracing",
            "Z": "zombie",
            "X": "dead",
            "I": "idle",
            "P": "parked",
        }
        state = str(selected.get("state", "?"))[:1]
        self.assertEqual(
            selected_card["state"], state_labels.get(state, f"state {state}")
        )
        command = selected.get("command", [])
        expected_command = (
            " ".join(command) if isinstance(command, list) else str(command)
        )
        self.assertEqual(selected_card["command"], expected_command)
        values = [str(value) for value in command] if isinstance(command, list) else []
        start = 0
        executable_name = Path(values[0].split(maxsplit=1)[0]).name if values else ""
        if (
            re.fullmatch(
                r"python(?:\d+(?:\.\d+)*)?|pypy\d*|bash|sh|zsh|fish|node|ruby|perl",
                executable_name.lower(),
            )
            and len(values) > 1
            and not values[1].startswith("-")
        ):
            start = 1
        focused = values[start:]
        if focused:
            match = re.fullmatch(r"(\s*)(\S+)([\s\S]*)", focused[0])
            if match:
                focused[0] = match[1] + Path(match[2]).name + match[3]
        self.assertEqual(
            selected_card["presentation"],
            {
                "command": " ".join(focused) if focused else expected_command,
                "launcher": f"via {executable_name}" if start == 1 else "",
            },
        )

        metrics = snapshot["metrics"]
        expected_metrics = [
            {
                "label": "CPU",
                "value": display_percent(metrics.get("cpuPercent")),
                "detail": (
                    "baseline"
                    if metrics.get("cpuStatus") == "baseline"
                    else "process share"
                ),
            },
            {
                "label": "MEM",
                "value": display_bytes(metrics.get("memoryBytes")),
                "detail": f"{metrics.get('threads', 0)} threads",
            },
            {
                "label": "DISK I/O",
                "value": (
                    "—"
                    if metrics.get("ioAvailable") is False
                    else display_rate(
                        int(metrics.get("readBytesPerSecond", 0) or 0)
                        + int(metrics.get("writeBytesPerSecond", 0) or 0)
                    )
                ),
                "detail": "read + write",
            },
            {
                "label": "GPU",
                "value": display_percent(metrics.get("gpuPercent")),
                "detail": f"{len(snapshot['devices']['gpu'])} clients",
            },
            {
                "label": "UPTIME",
                "value": display_duration(metrics.get("uptimeSeconds")),
                "detail": "paused" if snapshot.get("samplingPaused") else "live",
            },
        ]
        self.assertEqual(cards["metrics"], expected_metrics)
        cgroups = snapshot["context"].get("launch", {}).get("paths", [])
        runtime_expected = [
            (
                "Service",
                snapshot["context"].get("service", {}).get("id")
                or "No managing service found",
            ),
            (
                "Container",
                snapshot["context"].get("container", {}).get("name")
                or "No container found",
            ),
            (
                "Identity",
                f"UID {snapshot['security']['uid']} · GID {snapshot['security']['gid']}"
                if snapshot["security"].get("statusAvailable") is True
                else "Unavailable",
            ),
            (
                "Isolation",
                f"{len(snapshot['security'].get('namespaces', {}))} namespaces · "
                f"seccomp {snapshot['security'].get('seccomp') or 'unknown'}",
            ),
            (
                "Capabilities",
                (
                    ", ".join(snapshot["security"].get("capabilities", []))
                    or "No effective capabilities"
                )
                if snapshot["security"].get("capabilitiesKnown") is True
                else "Unknown",
            ),
            (
                "Control group",
                ", ".join(cgroups) if cgroups else "No control group identified",
            ),
        ]
        self.assertEqual(
            [(row["title"], row["subtitle"]) for row in cards["runtime"]],
            runtime_expected,
        )

    def _assert_device_summary(
        self, snapshot: dict[str, object], summary: dict[str, object]
    ) -> None:
        devices = snapshot["devices"]
        rows = summary["rows"]
        self.assertEqual(len(rows), 8)
        self.assertEqual(
            len(summary["activeRows"]), sum(row["active"] is True for row in rows)
        )
        expected_limited = sorted(
            name
            for name, state in devices.get("availability", {}).items()
            if state is False or state in {"unavailable", "partial"}
        )
        self.assertEqual(sorted(summary["limitedSources"]), expected_limited)
        kinds = (
            ("Microphone", "microphone"),
            ("Camera", "camera"),
            ("Screen capture", "screen"),
            ("Audio playback", "audio"),
            ("Audio capture", "audio-capture"),
            ("Video capture", "video"),
        )
        for title, kind in kinds:
            card = next(row for row in rows if row["title"] == title)
            matches = [
                row
                for row in devices["pipewire"]
                if row["kind"] == kind and row["active"] is True
            ]
            state = devices.get("availability", {}).get("pipewire", "available")
            if state in {False, "unavailable"}:
                self.assertEqual(card["meta"], "UNAVAILABLE")
            elif matches:
                self.assertEqual(card["meta"], f"{len(matches)} LIVE")
                self.assertTrue(card["active"])
            else:
                self.assertFalse(card["active"])
        gpu = next(row for row in rows if row["title"] == "GPU")
        inhibitors = next(row for row in rows if row["title"] == "Sleep inhibition")
        if devices["gpu"]:
            self.assertEqual(gpu["meta"], f"{len(devices['gpu'])} LIVE")
        if devices["inhibitors"]:
            self.assertEqual(inhibitors["meta"], f"{len(devices['inhibitors'])} LIVE")


if __name__ == "__main__":
    unittest.main()
