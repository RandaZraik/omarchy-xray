from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from live_backend import PROJECT_ROOT


QUICKSHELL = shutil.which("quickshell") or shutil.which("qs")
OMARCHY_IMPORTS = Path("/usr/share/omarchy/shell")
ORACLE = Path(__file__).with_name("ui_runtime_oracle.qml")
PUBLIC_ORACLE = Path(__file__).with_name("public_ui_oracle.qml")
TIMEOUT_ORACLE = Path(__file__).with_name("backend_timeout_oracle.qml")
PICKER_ORACLE = Path(__file__).with_name("picker_lifecycle_oracle.qml")
DRAWER_PERFORMANCE_ORACLE = Path(__file__).with_name(
    "drawer_performance_oracle.qml"
)


@unittest.skipUnless(
    QUICKSHELL and os.environ.get("WAYLAND_DISPLAY") and OMARCHY_IMPORTS.is_dir(),
    "requires a live Omarchy Quickshell session",
)
class UiRuntimeTests(unittest.TestCase):
    def test_large_drawer_sections_toggle_without_replacing_the_model(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            shutil.copy2(DRAWER_PERFORMANCE_ORACLE, config / "shell.qml")
            shutil.copytree(PROJECT_ROOT / "ui", config / "ui")
            shutil.copytree(OMARCHY_IMPORTS / "Commons", config / "Commons")
            shutil.copytree(OMARCHY_IMPORTS / "Ui", config / "Ui")
            completed = subprocess.run(
                [str(QUICKSHELL), "--path", str(config / "shell.qml")],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
                env={
                    **os.environ,
                    "XDG_STATE_HOME": str(root / "state"),
                },
            )
        output = completed.stdout + "\n" + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        marker = next(
            (
                line.partition("XRAY_DRAWER_PERF ")[2]
                for line in output.splitlines()
                if "XRAY_DRAWER_PERF " in line
            ),
            "",
        )
        self.assertTrue(marker, output)
        result = json.loads(marker)
        self.assertEqual(result["sourceCount"], 2500)
        self.assertEqual(result["resourceCount"], 1250)
        self.assertEqual(result["collapsedCount"], 1)
        self.assertEqual(result["expandedCount"], 1251)
        self.assertLess(result["collapseElapsedMs"], 250)
        self.assertLess(result["expandElapsedMs"], 250)

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

            completed = subprocess.run(
                [str(QUICKSHELL), "--path", str(root / "shell.qml")],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
                env={
                    **os.environ,
                    "XDG_STATE_HOME": str(root / "state"),
                    "XRAY_PICKER_EXPECTED_QUERY": expected_query,
                },
            )
        output = completed.stdout + "\n" + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertIn("XRAY_PICKER ok", output)
        self.assertNotIn("XRAY_PICKER_ERROR", output)

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

            completed = subprocess.run(
                [str(QUICKSHELL), "--path", str(root / "shell.qml")],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
            )
        output = completed.stdout + "\n" + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertIn("XRAY_BACKEND_TIMEOUT ok", output)
        self.assertNotIn("XRAY_BACKEND_TIMEOUT_ERROR", output)

    def test_shipped_entrypoints_cards_drilldowns_and_offline_mode_execute(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            (root / "home").mkdir()
            shutil.copy2(PUBLIC_ORACLE, config / "shell.qml")
            for name in ("XRay.qml", "BarWidget.qml"):
                shutil.copy2(PROJECT_ROOT / name, config / name)
            shutil.copytree(PROJECT_ROOT / "ui", config / "ui")
            shutil.copytree(PROJECT_ROOT / "backend", config / "backend")
            shutil.copytree(OMARCHY_IMPORTS / "Commons", config / "Commons")
            shutil.copytree(OMARCHY_IMPORTS / "Ui", config / "Ui")
            locked = root / "public-ui-oracle.txt"
            fixture = subprocess.Popen(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "tests/functional/truth_fixture.py"),
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
            completed = subprocess.run(
                [str(QUICKSHELL), "--path", str(config / "shell.qml")],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=85,
                check=False,
                env={
                    **os.environ,
                    "HOME": str(root / "home"),
                    "XDG_STATE_HOME": str(root / "state"),
                    "XRAY_UI_ORACLE_QUERY": f"pid:{truth['pid']}",
                    "XRAY_UI_ORACLE_PID": str(truth["pid"]),
                    "XRAY_UI_ORACLE_CHILD_PID": str(truth["childPid"]),
                    "XRAY_UI_ORACLE_PORT": str(truth["port"]),
                    "XRAY_UI_ORACLE_PATH": str(locked),
                },
            )
            output = completed.stdout + "\n" + completed.stderr
            self.assertEqual(completed.returncode, 0, output)
            marker = next(
                (
                    line.partition("XRAY_PUBLIC_UI ")[2]
                    for line in output.splitlines()
                    if "XRAY_PUBLIC_UI " in line
                ),
                "",
            )
            self.assertTrue(marker, output)
            result = json.loads(marker)
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
            config = root / "config"
            config.mkdir()
            shutil.copy2(ORACLE, config / "shell.qml")
            shutil.copytree(PROJECT_ROOT / "ui", config / "ui")
            shutil.copytree(PROJECT_ROOT / "backend", config / "backend")
            shutil.copytree(OMARCHY_IMPORTS / "Commons", config / "Commons")
            shutil.copytree(OMARCHY_IMPORTS / "Ui", config / "Ui")
            locked = root / "ui-oracle.txt"
            fixture = subprocess.Popen(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "tests/functional/truth_fixture.py"),
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
                    completed = subprocess.run(
                        [str(QUICKSHELL), "--path", str(config / "shell.qml")],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=20,
                        check=False,
                        env={
                            **os.environ,
                            "XDG_STATE_HOME": str(root / f"state-{width}"),
                            "XRAY_UI_ORACLE_QUERY": f"pid:{truth['pid']}",
                            "XRAY_UI_ORACLE_WIDTH": str(width),
                            "XRAY_UI_ORACLE_HEIGHT": str(height),
                        },
                    )
                    output = completed.stdout + "\n" + completed.stderr
                    self.assertEqual(completed.returncode, 0, output)
                    marker = next(
                        (
                            line.partition("XRAY_UI_RUNTIME ")[2]
                            for line in output.splitlines()
                            if "XRAY_UI_RUNTIME " in line
                        ),
                        "",
                    )
                    self.assertTrue(marker, output)
                    result = json.loads(marker)
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
