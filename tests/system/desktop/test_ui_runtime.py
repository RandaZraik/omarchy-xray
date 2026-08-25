from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from support.quickshell import (
    DRAWER_ENVIRONMENT_KEYS,
    PROJECT_ROOT,
    QuickshellHarness,
)


HARNESS = QuickshellHarness()
ORACLE_ROOT = Path(__file__).with_name("oracles")
ORACLE = ORACLE_ROOT / "ui_runtime_oracle.qml"
PUBLIC_ORACLE = ORACLE_ROOT / "public_ui_oracle.qml"
TIMEOUT_ORACLE = ORACLE_ROOT / "backend_timeout_oracle.qml"
PICKER_ORACLE = ORACLE_ROOT / "picker_lifecycle_oracle.qml"
DRAWER_SEARCH_ORACLE = (
    PROJECT_ROOT / "tests/support/oracles/drawer_search_oracle.qml"
)


@unittest.skipUnless(
    HARNESS.available,
    "requires a live Omarchy Quickshell session",
)
class UiRuntimeTests(unittest.TestCase):
    def _run_drawer_oracle(
        self,
        oracle: Path,
        marker_name: str,
        extra_env: dict[str, str] | None = None,
    ) -> dict:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shell = HARNESS.stage_plugin(root, oracle)
            completed = HARNESS.run(
                shell,
                timeout=35,
                environment=extra_env,
                unset_environment=DRAWER_ENVIRONMENT_KEYS,
                state_home=root / "state",
            )
        self.assertEqual(completed.returncode, 0, completed.output)
        return completed.json_marker(marker_name)

    def test_large_files_search_filters_and_restores_rows(self) -> None:
        result = self._run_drawer_oracle(
            DRAWER_SEARCH_ORACLE,
            "XRAY_DRAWER_SEARCH",
        )
        self.assertEqual(result["sourceCount"], 12000)
        self.assertEqual(result["resourceCount"], 3000)
        self.assertEqual(result["filteredCount"], 2)
        self.assertEqual(result["restoredCount"], 3001)

    def _run_picker(
        self, pick_data: dict[str, object], expected_query: str = ""
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ui").mkdir()
            (root / "backend").mkdir()
            shutil.copy2(PICKER_ORACLE, root / "shell.qml")
            shutil.copytree(PROJECT_ROOT / "ui/controllers", root / "ui/controllers")
            shutil.copy2(PROJECT_ROOT / "ui/BackendBridge.qml", root / "ui")
            shutil.copy2(PROJECT_ROOT / "ui/DetailDomains.js", root / "ui")
            shutil.copytree(PROJECT_ROOT / "ui/domains", root / "ui/domains")
            shutil.copy2(PROJECT_ROOT / "ui/Format.js", root / "ui")
            shutil.copy2(PROJECT_ROOT / "ui/DeviceSummary.js", root / "ui")
            (root / "backend/main.py").write_text(
                "import json\n"
                "import sys\n"
                "for line in sys.stdin:\n"
                "    request = json.loads(line)\n"
                "    command = request['command']\n"
                "    if command == 'bootstrap':\n"
                "        data = {'capabilities': {'windowPicker': True}, 'settings': {'refreshSeconds': 2, 'historySeconds': 300, 'capturePreview': False}, 'settingsDefaults': {'refreshSeconds': 2, 'historySeconds': 300, 'capturePreview': False}, 'settingsSpec': []}\n"
                "    elif command == 'pickWindow':\n"
                f"        data = {pick_data!r}\n"
                "    elif command in ('inspectFocused', 'catalog'):\n"
                "        data = {}\n"
                "    else:\n"
                "        data = {'closed': True}\n"
                "    print(json.dumps({'id': request['id'], 'ok': True, 'data': data}), flush=True)\n"
                "    if command == 'shutdown':\n"
                "        break\n",
                encoding="utf-8",
            )

            completed = HARNESS.run(
                root / "shell.qml",
                timeout=5,
                environment={
                    "XRAY_PICKER_EXPECTED_QUERY": expected_query,
                },
                state_home=root / "state",
            )
        self.assertEqual(completed.returncode, 0, completed.output)
        self.assertIn("XRAY_PICKER ok", completed.output)
        self.assertNotIn("XRAY_PICKER_ERROR", completed.output)

    def test_cancelled_window_picker_keeps_the_inspection_lifecycle_open(self) -> None:
        self._run_picker({"cancelled": True})

    def test_window_picker_synchronizes_the_resolved_window_query(self) -> None:
        self._run_picker(
            {
                "target": {
                    "kind": "window-point",
                    "value": "120,240",
                    "query": "window:0xabc",
                    "inspectionId": 1,
                }
            },
            "window:0xabc",
        )

    def test_backend_timeout_resolves_the_waiting_ui_callback(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ui").mkdir()
            (root / "backend").mkdir()
            shutil.copy2(TIMEOUT_ORACLE, root / "shell.qml")
            shutil.copy2(PROJECT_ROOT / "ui/BackendBridge.qml", root / "ui")
            (root / "backend/main.py").write_text(
                "import json\n"
                "from pathlib import Path\n"
                "import sys\n"
                "import time\n"
                "marker = Path(__file__).with_name('timed-out-once')\n"
                "for line in sys.stdin:\n"
                "    request = json.loads(line)\n"
                "    if request['command'] == 'pickWindow':\n"
                "        time.sleep(0.05)\n"
                "        data = {'picked': True}\n"
                "    elif not marker.exists():\n"
                "        marker.touch()\n"
                "        time.sleep(10)\n"
                "        continue\n"
                "    else:\n"
                "        data = {'ready': True}\n"
                "    print(json.dumps({'id': request['id'], 'ok': True, 'data': data}), flush=True)\n",
                encoding="utf-8",
            )

            completed = HARNESS.run(
                root / "shell.qml",
                timeout=5,
            )
        self.assertEqual(completed.returncode, 0, completed.output)
        self.assertIn("XRAY_BACKEND_TIMEOUT ok", completed.output)
        self.assertNotIn("XRAY_BACKEND_TIMEOUT_ERROR", completed.output)

    def test_shipped_entrypoints_cards_drilldowns_and_offline_mode_execute(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "home").mkdir()
            shell = HARNESS.stage_plugin(
                root,
                PUBLIC_ORACLE,
                include_backend=True,
                entrypoints=("XRay.qml", "BarWidget.qml"),
            )
            locked = root / "public-ui-oracle.txt"
            fixture = subprocess.Popen(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "tests/fixtures/truth_fixture.py"),
                    str(locked),
                ],
                cwd=directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "XRAY_TRUTH_FOREGROUND": "1"},
            )
            self.addCleanup(self._stop, fixture)
            assert fixture.stdout
            truth = json.loads(fixture.stdout.readline())
            completed = HARNESS.run(
                shell,
                timeout=85,
                environment={
                    "HOME": str(root / "home"),
                    "XRAY_UI_ORACLE_QUERY": f"pid:{truth['pid']}",
                    "XRAY_UI_ORACLE_PID": str(truth["pid"]),
                    "XRAY_UI_ORACLE_CHILD_PID": str(truth["childPid"]),
                    "XRAY_UI_ORACLE_PORT": str(truth["port"]),
                    "XRAY_UI_ORACLE_PATH": str(locked),
                },
                state_home=root / "state",
            )
            self.assertEqual(completed.returncode, 0, completed.output)
            result = completed.json_marker("XRAY_PUBLIC_UI")
            self.assertEqual(result["targetPid"], truth["pid"])
            self.assertTrue(result["offline"])
            self.assertGreater(result["inspectionId"], 0)
            self.assertTrue(Path(result["capsulePath"]).is_file())
            for event in (
                "publicEntry",
                "cardTruth",
                "drilldown",
                "settings",
                "offline",
            ):
                self.assertTrue(result["events"][event])

    def test_real_components_bridge_drawers_and_controls_execute(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shell = HARNESS.stage_plugin(root, ORACLE, include_backend=True)
            locked = root / "ui-oracle.txt"
            fixture = subprocess.Popen(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "tests/fixtures/truth_fixture.py"),
                    str(locked),
                ],
                cwd=directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "XRAY_TRUTH_FOREGROUND": "1"},
            )
            self.addCleanup(self._stop, fixture)
            assert fixture.stdout
            truth = json.loads(fixture.stdout.readline())
            for width, height in ((1000, 680), (1400, 840)):
                with self.subTest(width=width, height=height):
                    completed = HARNESS.run(
                        shell,
                        timeout=20,
                        environment={
                            "XRAY_UI_ORACLE_QUERY": f"pid:{truth['pid']}",
                            "XRAY_UI_ORACLE_WIDTH": str(width),
                            "XRAY_UI_ORACLE_HEIGHT": str(height),
                        },
                        state_home=root / f"state-{width}",
                    )
                    self.assertEqual(completed.returncode, 0, completed.output)
                    result = completed.json_marker("XRAY_UI_RUNTIME")
                    self.assertEqual(result["targetPid"], truth["pid"])
                    self.assertGreaterEqual(result["processRows"], 2)
                    self.assertGreaterEqual(result["filteredRows"], 1)
                    self.assertEqual(result["headerHeight"], 42)
                    self.assertEqual(result["footerHeight"], 38)
                    self.assertTrue(result["fontFamily"])

    @staticmethod
    def _stop(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()
