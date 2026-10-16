import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from support.markers import parse_json_marker
from support.quickshell import QuickshellHarness
from support.slowdown import SlowdownFixture
from xray.evidence.slowdown import diagnose
from xray.processes.slowdown import SlowdownSampler


HARNESS = QuickshellHarness()
QML = shutil.which("qml6") or shutil.which("qml")
ORACLES = Path(__file__).with_name("oracles")


def performance_snapshot(root: Path) -> dict[str, object]:
    fixture = SlowdownFixture(root)
    sampler = SlowdownSampler()
    sampler.sample(fixture.proc, fixture.rows(), now=1)
    fixture.write_group(
        "/apps/demo",
        "cpu.stat",
        "nr_periods 120\nnr_throttled 100\nthrottled_usec 6000000\n",
    )
    result = diagnose(sampler.sample(fixture.proc, fixture.rows(), now=3))
    return {"target": {"rootPid": 7}, "performance": result}


@unittest.skipUnless(
    HARNESS.executable and HARNESS.imports.is_dir(),
    "requires Quickshell and Omarchy QML imports (no desktop required)",
)
class HeadlessPerformanceUiTests(unittest.TestCase):
    def test_keyboard_navigation_and_focus_survive_performance_refresh(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = performance_snapshot(root)
            shell = HARNESS.stage_plugin(
                root, ORACLES / "performance_keyboard_oracle.qml"
            )
            completed = HARNESS.run_offscreen(
                shell,
                timeout=12,
                state_home=root / "state",
                environment={
                    "XRAY_PERFORMANCE_FIXTURE": json.dumps(snapshot),
                },
            )
        self.assertEqual(completed.returncode, 0, completed.output)
        result = completed.json_marker("XRAY_PERFORMANCE_KEYBOARD")
        self.assertGreater(
            result["visitedRows"], len(snapshot["performance"]["checks"])
        )
        self.assertTrue(
            all(
                result[key]
                for key in (
                    "scrolled",
                    "expanded",
                    "refreshed",
                    "searchFocus",
                    "tabFocus",
                )
            )
        )
        self.assertNotIn("TypeError", completed.output)
        self.assertNotIn("Binding loop", completed.output)

    def test_real_backend_updates_the_open_drawer_offscreen(self) -> None:
        process = subprocess.Popen(["sleep", "60"])
        self.addCleanup(process.wait, timeout=3)
        self.addCleanup(process.terminate)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shell = HARNESS.stage_plugin(
                root, ORACLES / "performance_live_oracle.qml", include_backend=True
            )
            completed = HARNESS.run_offscreen(
                shell,
                timeout=15,
                state_home=root / "state",
                environment={
                    "XRAY_LIVE_PID": str(process.pid),
                },
            )
        self.assertEqual(completed.returncode, 0, completed.output)
        result = completed.json_marker("XRAY_LIVE_PERFORMANCE")
        self.assertEqual(result["pid"], process.pid)
        self.assertEqual(result["status"], "Quiet")
        self.assertTrue(result["refreshed"])
        self.assertGreater(result["checks"], 0)
        self.assertNotIn("TypeError", completed.output)
        self.assertNotIn("Binding loop", completed.output)

    def test_real_button_drawer_search_evidence_and_offline_report(self) -> None:
        for width in (850, 1400):
            with self.subTest(width=width), TemporaryDirectory() as directory:
                root = Path(directory)
                snapshot = performance_snapshot(root)
                shell = HARNESS.stage_plugin(root, ORACLES / "performance_oracle.qml")
                completed = HARNESS.run_offscreen(
                    shell,
                    timeout=15,
                    state_home=root / "state",
                    environment={
                        "XRAY_PERFORMANCE_FIXTURE": json.dumps(snapshot),
                        "XRAY_PERFORMANCE_WIDTH": str(width),
                        "XRAY_PERFORMANCE_SCREENSHOT": os.environ.get(
                            "XRAY_PERFORMANCE_SCREENSHOT", ""
                        ),
                    },
                )
                self.assertEqual(completed.returncode, 0, completed.output)
                result = completed.json_marker("XRAY_PERFORMANCE")
                self.assertEqual(
                    result["checks"], len(snapshot["performance"]["checks"])
                )
                self.assertTrue(
                    all(
                        result[key]
                        for key in (
                            "overview",
                            "clicked",
                            "filtered",
                            "refreshed",
                            "collapsed",
                            "offline",
                            "legacy",
                        )
                    )
                )
                self.assertNotIn("Binding loop", completed.output)
                self.assertNotIn("Unable to assign", completed.output)
                self.assertNotIn("TypeError", completed.output)


@unittest.skipUnless(QML, "requires Qt QML runtime")
class PerformanceDomainTests(unittest.TestCase):
    def test_assessment_preserves_uncertainty_units_and_shared_scope(self) -> None:
        completed = subprocess.run(
            [
                QML,
                "-platform",
                "offscreen",
                str(ORACLES / "performance_assessment_oracle.qml"),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "QT_FORCE_STDERR_LOGGING": "1"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = parse_json_marker(
            completed.stdout + completed.stderr, "XRAY_ASSESSMENT"
        )
        self.assertEqual(result["failures"], [])

    def test_performance_domain_preserves_status_scope_search_and_updates(self) -> None:
        with TemporaryDirectory() as directory:
            snapshot = performance_snapshot(Path(directory))
            completed = subprocess.run(
                [
                    QML,
                    "-platform",
                    "offscreen",
                    str(ORACLES / "performance_logic_oracle.qml"),
                    "--",
                    json.dumps(snapshot),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "QT_FORCE_STDERR_LOGGING": "1"},
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = parse_json_marker(
            completed.stdout + completed.stderr, "XRAY_PERFORMANCE_LOGIC"
        )
        self.assertEqual(result["count"], len(snapshot["performance"]["checks"]))
        self.assertEqual(result["sections"], ["cpu", "memory", "io"])
        self.assertEqual(result["first"]["meta"], "OBSERVED")
        self.assertIn("throttled periods", " ".join(result["first"]["evidence"]))
        self.assertGreater(result["searchCount"], 0)
        self.assertTrue(result["touches"])
        self.assertFalse(result["unrelated"])
        self.assertEqual(result["legacy"][0]["meta"], "UNAVAILABLE")
