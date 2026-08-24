from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import sys
import shutil
from tempfile import TemporaryDirectory
import unittest
import zipfile
from itertools import product
import time

from live_backend import LiveBackend, PROJECT_ROOT, wait_until
from machine_truth import (
    descriptor_info,
    expected_detail_counts,
    proc_security,
    proc_status,
    rendered_details,
    system_cpu_ticks,
)


QML_EXECUTABLE = shutil.which("qml6") or shutil.which("qml")


class LiveTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = TemporaryDirectory(prefix=".xray-truth-", dir=Path.home())
        cls.root = Path(cls.temporary.name)
        cls.locked_path = cls.root / "owned evidence.txt"
        cls.secret = "xray-fixture-secret-should-never-escape"
        environment = dict(os.environ)
        environment["XRAY_TRUTH_MARKER"] = "known-environment-value-must-stay-private"
        cls.fixture = subprocess.Popen(
            [
                sys.executable,
                str(PROJECT_ROOT / "tests/functional/truth_fixture.py"),
                str(cls.locked_path),
                "--api-key",
                cls.secret,
            ],
            cwd=cls.root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert cls.fixture.stdout
        ready = cls.fixture.stdout.readline()
        if not ready:
            error = cls.fixture.stderr.read() if cls.fixture.stderr else ""
            raise AssertionError(f"truth fixture failed to start: {error}")
        cls.truth = json.loads(ready)
        cls.backend = LiveBackend(cls.root / "state")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.backend.close()
        fixture_pid = int(cls.truth["pid"])
        if Path(f"/proc/{fixture_pid}").exists():
            os.kill(fixture_pid, 15)
            wait_until(lambda: not Path(f"/proc/{fixture_pid}").exists())
        cls.fixture.wait(timeout=3.0)
        if cls.fixture.stdout:
            cls.fixture.stdout.close()
        if cls.fixture.stderr:
            cls.fixture.stderr.close()
        cls.temporary.cleanup()

    def require_ok(self, response: dict[str, object]) -> dict[str, object]:
        self.assertTrue(response.get("ok"), response)
        data = response.get("data")
        self.assertIsInstance(data, dict)
        return data

    def inspect_fixture(self) -> dict[str, object]:
        return self.require_ok(
            self.backend.request("inspect", query=f"pid:{self.truth['pid']}")
        )

    def test_01_fixture_truth_is_independently_proven(self) -> None:
        os.kill(int(self.truth["pid"]), 0)
        os.kill(int(self.truth["childPid"]), 0)
        self.assertEqual(
            Path(f"/proc/{self.truth['pid']}/cwd").resolve(), self.root.resolve()
        )
        self.assertEqual(
            Path(f"/proc/{self.truth['pid']}/comm").read_text().strip(), "xray-truth"
        )

        with socket.create_connection(
            ("127.0.0.1", int(self.truth["port"])), timeout=2.0
        ):
            pass
        with self.locked_path.open("r+") as contender:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_02_bootstrap_contract_is_complete(self) -> None:
        bootstrap = self.require_ok(self.backend.request("bootstrap"))
        self.assertEqual(
            {row["key"] for row in bootstrap["settingsSpec"]},
            {"refreshSeconds", "historySeconds", "capturePreview"},
        )
        self.assertEqual(
            bootstrap["settings"],
            {
                "refreshSeconds": 2.0,
                "historySeconds": 300,
                "capturePreview": False,
            },
        )
        self.assertEqual(
            bootstrap["settingsDefaults"],
            {"refreshSeconds": 2, "historySeconds": 300, "capturePreview": False},
        )
        self.assertNotIn("catalog", bootstrap)
        self.assertIn("capabilities", bootstrap)

    def test_02b_invalid_and_oversized_frames_fail_without_killing_the_backend(
        self,
    ) -> None:
        self.assertFalse(self.backend.raw("not-json")["ok"])
        self.assertIn("size limit", self.backend.raw(" " * 1_048_577)["error"])
        self.assertTrue(self.backend.request("bootstrap")["ok"])

    def test_03_pid_inspection_matches_every_known_owner(self) -> None:
        snapshot = self.inspect_fixture()
        self.assertEqual(snapshot["target"]["rootPid"], self.truth["pid"])
        self.assertEqual(snapshot["target"]["ownerPid"], self.truth["pid"])
        self.assertEqual(snapshot["context"]["workingDirectory"], str(self.root))

        processes = {row["pid"]: row for row in snapshot["processes"]}
        self.assertIn(self.truth["pid"], processes)
        self.assertIn(self.truth["childPid"], processes)
        root = processes[self.truth["pid"]]
        self.assertEqual(root["name"], "xray-truth")
        self.assertIn("XRAY_TRUTH_MARKER", root["environmentNames"])
        self.assertNotIn(
            "known-environment-value-must-stay-private", json.dumps(snapshot)
        )
        self.assertNotIn(self.secret, json.dumps(snapshot))
        self.assertIn("<redacted>", root["command"])

        listener = next(
            row
            for row in snapshot["connections"]
            if row["localPort"] == self.truth["port"] and row["listening"]
        )
        self.assertEqual(listener["localAddress"], "127.0.0.1")
        self.assertIn(self.truth["pid"], listener["pids"])

        owned_file = next(
            row for row in snapshot["files"] if row["target"] == str(self.locked_path)
        )
        self.assertEqual(owned_file["pid"], self.truth["pid"])
        self.assertEqual(owned_file["mode"], "read/write")
        self.assertTrue(
            any(row["pid"] == self.truth["pid"] for row in snapshot["locks"])
        )

    @unittest.skipUnless(QML_EXECUTABLE, "requires a Qt QML runtime")
    def test_03a_every_live_card_drilldown_preserves_backend_truth(self) -> None:
        snapshot = self.inspect_fixture()
        rendered = rendered_details(snapshot)
        context = snapshot["context"]
        expected_counts = expected_detail_counts(snapshot)
        self.assertEqual(rendered["counts"], expected_counts)
        for domain, count in expected_counts.items():
            with self.subTest(domain=domain):
                self.assertEqual(count, len(rendered["rows"][domain]))

        rows = rendered["rows"]
        self.assertTrue(
            any(
                f"PID {self.truth['pid']}" in row["subtitle"]
                for row in rows["processes"]
            )
        )
        self.assertTrue(
            any(str(self.truth["port"]) in row["title"] for row in rows["connections"])
        )
        self.assertTrue(
            any(row["title"] == str(self.locked_path) for row in rows["files"])
        )
        self.assertTrue(
            any(row["title"] == "Kernel file lock" for row in rows["files"])
        )
        runtime = {row["title"]: row for row in rows["runtime"]}
        self.assertEqual(
            runtime["Executable"]["subtitle"],
            str(Path(f"/proc/{self.truth['pid']}/exe").resolve()),
        )
        self.assertEqual(runtime["Working directory"]["subtitle"], str(self.root))
        for node, row in zip(context["cause"]["nodes"], rows["cause"], strict=True):
            self.assertIn(node["title"], row["title"])
            self.assertEqual(row["subtitle"], node.get("proof") or node.get("detail"))
        rendered_explanations = rows["explanations"]
        for explanation in snapshot["explanations"]:
            rendered_finding = next(
                row
                for row in rendered_explanations
                if row["title"] == explanation["title"]
            )
            self.assertEqual(
                rendered_finding["evidence"], explanation.get("evidence", [])
            )
            if explanation.get("nextStep"):
                self.assertEqual(rendered_finding["nextStep"], explanation["nextStep"])
        coverage_titles = {row["title"] for row in rows["coverage"]}
        self.assertEqual(
            coverage_titles,
            set(snapshot["coverage"]["available"])
            | set(snapshot["coverage"]["limited"]),
        )
        self.assertTrue(
            any(
                row.get("pid") == self.truth["pid"] and row["meta"] == "SELECTED"
                for row in rows["alternatives"]
            )
        )
        self.assertEqual(
            rendered["details"]["files"],
            f"{len(snapshot['files'])} descriptors  ·  {len(snapshot['locks'])} locks",
        )
        self.assertEqual(
            rendered["cards"]["processSummary"],
            {
                "processes": len(snapshot["processes"]),
                "threads": sum(row["threads"] for row in snapshot["processes"]),
                "memoryBytes": sum(row["memoryBytes"] for row in snapshot["processes"]),
            },
        )
        for domain, sections in rendered["sections"].items():
            if sections:
                with self.subTest(section_totals=domain):
                    self.assertEqual(
                        sum(section["sourceCount"] for section in sections),
                        rendered["counts"][domain],
                    )
        file_summary = {
            row["label"]: row["value"] for row in rendered["summaries"]["files"]
        }
        self.assertEqual(file_summary["DESCRIPTORS"], str(len(snapshot["files"])))
        self.assertEqual(file_summary["LOCKS"], str(len(snapshot["locks"])))
        self.assertEqual(
            file_summary["DELETED"],
            str(sum(row["deleted"] for row in snapshot["files"])),
        )

    def test_03b_performance_and_security_cards_match_procfs(self) -> None:
        initial = self.inspect_fixture()
        pid = int(self.truth["pid"])
        descriptor_before = {
            (int(row["pid"]), int(row["fd"]), str(row["target"])): descriptor_info(
                int(row["pid"]), int(row["fd"])
            )
            for row in initial["files"]
        }
        stat_before = Path(f"/proc/{pid}/stat").read_text()
        io_before = Path(f"/proc/{pid}/io").read_text()
        total_cpu_before = system_cpu_ticks()
        sampled_before = time.monotonic()
        time.sleep(0.35)
        snapshot = self.require_ok(self.backend.request("refresh"))
        sampled_after = time.monotonic()
        total_cpu_after = system_cpu_ticks()
        stat_after = Path(f"/proc/{pid}/stat").read_text()
        io_after = Path(f"/proc/{pid}/io").read_text()
        status = proc_status(pid)
        root = next(row for row in snapshot["processes"] if row["pid"] == pid)
        self.assertEqual(root["uid"], int(status["Uid"].split()[0]))
        self.assertEqual(root["user"], pwd.getpwuid(root["uid"]).pw_name)
        self.assertEqual(root["gid"], int(status["Gid"].split()[0]))
        self.assertEqual(root["threads"], int(status["Threads"]))
        page_size = os.sysconf("SC_PAGE_SIZE")
        rss_before = int(stat_before.rsplit(")", 1)[1].split()[21]) * page_size
        rss_after = int(stat_after.rsplit(")", 1)[1].split()[21]) * page_size
        self.assertEqual(root["memoryBytes"] % page_size, 0)
        self.assertGreaterEqual(root["memoryBytes"], min(rss_before, rss_after))
        self.assertLessEqual(root["memoryBytes"], max(rss_before, rss_after))

        metrics = snapshot["metrics"]
        self.assertEqual(metrics["processCount"], len(snapshot["processes"]))
        self.assertEqual(
            metrics["memoryBytes"],
            sum(row["memoryBytes"] for row in snapshot["processes"]),
        )
        self.assertEqual(
            metrics["threads"], sum(row["threads"] for row in snapshot["processes"])
        )
        self.assertGreaterEqual(metrics["cpuPercent"], 0)
        self.assertGreaterEqual(metrics["readBytesPerSecond"], 0)
        self.assertGreater(metrics["writeBytesPerSecond"], 0)
        cpu_before = sum(map(int, stat_before.rsplit(")", 1)[1].split()[11:13]))
        cpu_after = sum(map(int, stat_after.rsplit(")", 1)[1].split()[11:13]))
        self.assertGreater(cpu_after, cpu_before)
        self.assertGreater(root["cpuPercent"], 0)
        self.assertGreater(metrics["cpuPercent"], 0)
        self.assertGreater(root["writeBytesPerSecond"], 0)
        expected_cpu = (
            (cpu_after - cpu_before) / max(1, total_cpu_after - total_cpu_before) * 100
        )
        # The independent reads bracket, rather than occur at the exact same
        # instant as, the backend sample. One percentage point covers that
        # unavoidable scheduling edge while still catching per-core vs total
        # machine-capacity mistakes.
        self.assertLessEqual(abs(root["cpuPercent"] - expected_cpu), 1.0)
        io_values_before = {
            line.partition(":")[0]: int(line.partition(":")[2])
            for line in io_before.splitlines()
        }
        io_values_after = {
            line.partition(":")[0]: int(line.partition(":")[2])
            for line in io_after.splitlines()
        }
        self.assertGreater(
            io_values_after["write_bytes"], io_values_before["write_bytes"]
        )
        expected_write_rate = (
            io_values_after["write_bytes"] - io_values_before["write_bytes"]
        ) / (sampled_after - sampled_before)
        self.assertLessEqual(
            abs(root["writeBytesPerSecond"] - expected_write_rate),
            max(16_384, expected_write_rate * 0.25),
        )

        security = snapshot["security"]
        raw_security = proc_security(pid)
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
            with self.subTest(security_field=key):
                self.assertEqual(security[key], raw_security[key])

        for row in snapshot["files"]:
            try:
                current_target = os.readlink(f"/proc/{row['pid']}/fd/{row['fd']}")
            except OSError:
                continue
            if current_target != row["target"]:
                continue
            info = descriptor_info(int(row["pid"]), int(row["fd"]))
            if info is None or "mode" not in row:
                continue
            identity = (int(row["pid"]), int(row["fd"]), str(row["target"]))
            for key in ("flags", "mode", "mountId"):
                with self.subTest(descriptor=(row["pid"], row["fd"]), field=key):
                    self.assertEqual(row[key], info[key])
            before = descriptor_before.get(identity)
            if before is not None:
                self.assertGreaterEqual(
                    row["position"], min(before["position"], info["position"])
                )
                self.assertLessEqual(
                    row["position"], max(before["position"], info["position"])
                )

    def test_04_port_file_and_application_queries_resolve_the_same_truth(self) -> None:
        with socket.create_connection(
            ("127.0.0.1", int(self.truth["port"])), timeout=2.0
        ):
            snapshot = self.require_ok(
                self.backend.request("inspect", query=f":{self.truth['port']}")
            )
            self.assertEqual(snapshot["target"]["kind"], "port")
            self.assertEqual(snapshot["target"]["ownerPid"], self.truth["pid"])
            self.assertEqual(snapshot["target"]["rootPid"], self.truth["pid"])

        queries = (
            (f"file:{self.locked_path}", "file"),
            ("xray-truth", "application"),
        )
        for query, kind in queries:
            with self.subTest(query=query):
                snapshot = self.require_ok(self.backend.request("inspect", query=query))
                self.assertEqual(snapshot["target"]["kind"], kind)
                self.assertEqual(snapshot["target"]["ownerPid"], self.truth["pid"])
                self.assertEqual(snapshot["target"]["rootPid"], self.truth["pid"])

    def test_05_catalog_contains_the_known_listener_and_process_owner(self) -> None:
        catalog = self.require_ok(self.backend.request("catalog"))
        listener = next(
            row for row in catalog["ports"] if row["localPort"] == self.truth["port"]
        )
        self.assertIn(self.truth["pid"], listener["pids"])

    def test_06_live_connection_appears_after_baseline(self) -> None:
        self.inspect_fixture()
        client = socket.create_connection(
            ("127.0.0.1", int(self.truth["port"])), timeout=2.0
        )
        self.addCleanup(client.close)

        def connection_visible() -> bool:
            snapshot = self.require_ok(self.backend.request("refresh"))
            return any(
                row["localPort"] == self.truth["port"] and row["state"] == "Established"
                for row in snapshot["connections"]
            )

        self.assertTrue(wait_until(connection_visible, timeout=4.0))
        snapshot = self.require_ok(self.backend.request("refresh"))
        self.assertTrue(
            any(
                event["domain"] == "connections" and event["kind"] == "added"
                for event in snapshot["timeline"]
            ),
            snapshot["timeline"],
        )

    def test_06b_reset_baseline_clears_every_change_domain(self) -> None:
        self.inspect_fixture()
        reset = self.require_ok(self.backend.request("resetBaseline"))

        self.assertEqual(reset["timeline"], [])
        for change in reset["changes"]["domains"].values():
            self.assertEqual(change, {"added": 0, "removed": 0})

    def test_06bb_compact_refresh_is_a_complete_mergeable_live_snapshot(self) -> None:
        initial = self.inspect_fixture()

        compact = self.require_ok(self.backend.request("refresh", compact=True))

        self.assertEqual(set(compact), {"snapshotPatch"})
        patch = compact["snapshotPatch"]
        self.assertIsInstance(patch, dict)
        merged = {**initial, **patch}
        self.assertEqual(merged["target"]["rootPid"], self.truth["pid"])
        self.assertIn(
            self.truth["childPid"], {row["pid"] for row in merged["processes"]}
        )
        self.assertTrue(
            any(
                row["localPort"] == self.truth["port"] and row["listening"]
                for row in merged["connections"]
            )
        )
        self.assertTrue(
            any(row["target"] == str(self.locked_path) for row in merged["files"])
        )
        self.assertEqual(merged["metrics"]["processCount"], len(merged["processes"]))

    def test_06c_sampling_pause_freezes_refresh_until_resumed(self) -> None:
        initial = self.inspect_fixture()
        try:
            paused = self.require_ok(
                self.backend.request("setSamplingPaused", paused=True)
            )
            self.assertTrue(paused["samplingPaused"])

            frozen = self.require_ok(self.backend.request("refresh"))
            self.assertTrue(frozen["samplingPaused"])
            self.assertEqual(frozen["target"], initial["target"])
            self.assertEqual(frozen["metrics"], initial["metrics"])
        finally:
            resumed = self.require_ok(
                self.backend.request("setSamplingPaused", paused=False)
            )
        self.assertFalse(resumed["samplingPaused"])
        self.assertFalse(
            self.require_ok(self.backend.request("refresh"))["samplingPaused"]
        )

    def test_06d_closing_an_inspection_clears_session_state(self) -> None:
        self.inspect_fixture()
        closed = self.require_ok(self.backend.request("closeInspection"))
        self.assertTrue(closed["closed"])
        self.assertFalse(self.backend.request("refresh")["ok"])
        self.assertEqual(self.inspect_fixture()["target"]["rootPid"], self.truth["pid"])

    def test_07_all_settings_values_apply_and_persist(self) -> None:
        combinations = tuple(
            {
                "refreshSeconds": refresh,
                "historySeconds": history,
                "capturePreview": preview,
            }
            for refresh, history, preview in product(
                (1, 2, 5, 10),
                (60, 300, 900),
                (False, True),
            )
        )
        for settings in combinations:
            with self.subTest(settings=settings):
                saved = self.require_ok(
                    self.backend.request("configure", settings=settings)
                )
                self.assertEqual(saved, settings)

        self.backend.close()
        self.__class__.backend = LiveBackend(self.root / "state")
        bootstrap = self.require_ok(self.backend.request("bootstrap"))
        self.assertEqual(bootstrap["settings"], combinations[-1])

        settings_file = self.root / "state/omarchy-xray/settings.json"
        self.assertEqual(settings_file.stat().st_mode & 0o777, 0o600)
        self.require_ok(
            self.backend.request(
                "configure",
                settings={
                    "refreshSeconds": 2,
                    "historySeconds": 300,
                    "capturePreview": False,
                },
            )
        )

    def test_08_capsule_round_trip_is_exact_private_and_offline(self) -> None:
        snapshot = self.inspect_fixture()
        exported = self.require_ok(
            self.backend.request("exportCapsule", directory=str(self.root))
        )
        path = Path(exported["path"])
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

        raw = path.read_bytes()
        self.assertNotIn(self.secret.encode(), raw)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.namelist(), ["capsule.json"])
            capsule = json.loads(archive.read("capsule.json"))
        serialized = json.dumps(capsule)
        self.assertNotIn(self.secret, serialized)
        self.assertNotIn("known-environment-value-must-stay-private", serialized)
        command = next(
            row
            for row in capsule["snapshot"]["processes"]
            if row["pid"] == self.truth["pid"]
        )["command"]
        self.assertIn("<redacted>", command)

        opened = self.require_ok(self.backend.request("openCapsule", path=str(path)))
        self.assertEqual(
            opened["snapshot"]["target"]["rootPid"], snapshot["target"]["rootPid"]
        )
        compared = self.require_ok(
            self.backend.request("compareCapsule", path=str(path))
        )
        self.assertEqual(compared["domains"]["processes"]["added"], 0)
        self.assertEqual(compared["domains"]["processes"]["removed"], 0)

    def test_09_report_contains_measured_facts_not_secrets(self) -> None:
        self.inspect_fixture()
        report = self.require_ok(self.backend.request("report"))["text"]
        self.assertIn(f"PID: {self.truth['pid']}", report)
        self.assertIn("Processes:", report)
        self.assertNotIn(self.secret, report)

    def test_10_pause_and_resume_match_the_kernel_state(self) -> None:
        snapshot = self.inspect_fixture()
        inspection_id = snapshot["target"]["inspectionId"]
        paused = self.require_ok(
            self.backend.request("action", action="pause", inspectionId=inspection_id)
        )
        self.assertTrue(paused["ok"], paused)
        stat_path = Path(f"/proc/{self.truth['pid']}/stat")
        self.assertTrue(
            wait_until(
                lambda: stat_path.read_text().rsplit(")", 1)[1].split()[0] == "T"
            )
        )

        resumed = self.require_ok(
            self.backend.request("action", action="resume", inspectionId=inspection_id)
        )
        self.assertTrue(resumed["ok"], resumed)
        self.assertTrue(
            wait_until(
                lambda: stat_path.read_text().rsplit(")", 1)[1].split()[0] != "T"
            )
        )

    def test_99_unmanaged_relaunch_is_rejected_and_terminate_matches_liveness(
        self,
    ) -> None:
        with TemporaryDirectory(prefix=".xray-action-truth-", dir=Path.home()) as temp:
            root = Path(temp)
            fixture = subprocess.Popen(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "tests/functional/truth_fixture.py"),
                    str(root / "owned evidence.txt"),
                ],
                cwd=root,
                env={**os.environ, "XRAY_TRUTH_FOREGROUND": "1"},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.addCleanup(self._stop_process, fixture)
            assert fixture.stdout
            truth = json.loads(fixture.stdout.readline())
            fixture_pid = int(truth["pid"])
            with LiveBackend(root / "state") as backend:
                snapshot = self.require_ok(
                    backend.request("inspect", query=f"pid:{fixture_pid}")
                )
                inspection_id = snapshot["target"]["inspectionId"]
                relaunched = self.require_ok(
                    backend.request(
                        "action", action="relaunch", inspectionId=inspection_id
                    )
                )
                self.assertFalse(relaunched["ok"], relaunched)
                self.assertIn(
                    "user service or container manager", relaunched["message"]
                )
                self.assertTrue(Path(f"/proc/{fixture_pid}").exists())

                terminated = self.require_ok(
                    backend.request(
                        "action", action="terminate", inspectionId=inspection_id
                    )
                )
                self.assertTrue(terminated["ok"], terminated)
                fixture_path = Path(f"/proc/{fixture_pid}")
                self.assertTrue(wait_until(lambda: fixture.poll() is not None))
                self.assertFalse(fixture_path.exists())
                missing = self.require_ok(
                    backend.request("inspect", query=f"pid:{fixture_pid}")
                )
                self.assertEqual(missing["target"]["rootPid"], 0)
                statuses = {
                    "no-owner": "No matching process",
                    "limited": "Some data unavailable",
                }
                status_code = missing["coverage"]["statusCode"]
                self.assertIn(status_code, statuses)
                self.assertEqual(missing["coverage"]["status"], statuses[status_code])
                if status_code == "limited":
                    self.assertTrue(missing["coverage"]["limited"])

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()
