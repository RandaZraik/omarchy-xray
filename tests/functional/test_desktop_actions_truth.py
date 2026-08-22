from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlparse

from live_backend import wait_until

from xray.actions.process_control import ProcessActions
from xray.processes.identity import identity_for
from xray.runtime.context import list_windows
from xray.system.commands import CommandRunner
from xray.system.procfs import ProcFs


HAS_DESKTOP = bool(
    os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    and shutil.which("hyprctl")
    and shutil.which("xdg-open")
    and shutil.which("xdg-terminal-exec")
)


@unittest.skipUnless(HAS_DESKTOP, "requires a live Hyprland desktop")
class DesktopActionTruthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proc = ProcFs()
        self.runner = CommandRunner()
        self.actions = ProcessActions(self.proc, self.runner)

    def _window_addresses(self) -> set[str]:
        windows, error = list_windows(self.runner)
        self.assertEqual(error, "")
        return {str(window["address"]) for window in windows}

    def _new_windows(self, before: set[str]) -> list[dict[str, object]]:
        windows, error = list_windows(self.runner)
        self.assertEqual(error, "")
        return [window for window in windows if window["address"] not in before]

    def _close_windows(self, addresses: set[str]) -> None:
        for address in addresses:
            selector = f"address:{address}"
            result = self.runner.run(
                [
                    "hyprctl",
                    "dispatch",
                    f'hl.dsp.window.close({{ window = "{selector}" }})',
                ]
            )
            if result.returncode != 0:
                self.runner.run(["hyprctl", "dispatch", "closewindow", selector])

    @staticmethod
    def _pids_in_directory(directory: Path) -> set[int]:
        result: set[int] = set()
        for candidate in Path("/proc").iterdir():
            if not candidate.name.isdigit():
                continue
            try:
                if (candidate / "cwd").resolve() == directory.resolve():
                    result.add(int(candidate.name))
            except OSError:
                continue
        return result

    def test_terminal_opens_the_selected_working_directory(self) -> None:
        with TemporaryDirectory(prefix="xray-desktop-action-") as directory:
            working_directory = Path(directory)
            target = subprocess.Popen(["sleep", "30"], cwd=working_directory)
            opened: set[str] = set()
            try:
                identity = identity_for(self.proc, target.pid)
                self.assertIsNotNone(identity)
                assert identity
                context = {"workingDirectory": str(working_directory)}

                before = self._window_addresses()
                known_cwds = self._pids_in_directory(working_directory)
                terminal = self.actions.perform("terminal", identity, context)
                self.assertTrue(terminal.ok, terminal.message)
                self.assertTrue(
                    wait_until(
                        lambda: bool(self._window_addresses() - before), timeout=5.0
                    ),
                    "the desktop did not create a terminal window",
                )
                terminal_windows = self._new_windows(before)
                opened.update(str(window["address"]) for window in terminal_windows)
                self.assertTrue(
                    wait_until(
                        lambda: bool(
                            self._pids_in_directory(working_directory) - known_cwds
                        ),
                        timeout=5.0,
                    ),
                    "the new terminal did not inherit the selected directory",
                )

            finally:
                self._close_windows(opened)
                if target.poll() is None:
                    target.terminate()
                target.wait(timeout=3.0)
                self.assertTrue(
                    wait_until(
                        lambda: self.runner.active_launchers() == 0, timeout=10.0
                    ),
                    "the terminal launcher did not exit after its window closed",
                )

    def test_reveal_routes_the_exact_directory_through_xdg(self) -> None:
        with TemporaryDirectory(prefix="xray-reveal-action-") as directory:
            root = Path(directory)
            working_directory = root / "selected directory"
            working_directory.mkdir()
            marker = root / "opened.txt"
            opener = root / "opener.py"
            opener.write_text(
                "#!/usr/bin/python3\n"
                "from pathlib import Path\n"
                "import sys\n"
                f"Path({str(marker)!r}).write_text(sys.argv[-1], encoding='utf-8')\n",
                encoding="utf-8",
            )
            opener.chmod(0o700)
            applications = root / "data/applications"
            applications.mkdir(parents=True)
            (applications / "xray-test-opener.desktop").write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=X-Ray Test Opener\n"
                f"Exec={opener} %u\n"
                "MimeType=inode/directory;\n"
                "NoDisplay=true\n",
                encoding="utf-8",
            )
            config = root / "config"
            config.mkdir()
            (config / "mimeapps.list").write_text(
                "[Default Applications]\ninode/directory=xray-test-opener.desktop\n",
                encoding="utf-8",
            )
            target = subprocess.Popen(["sleep", "30"], cwd=working_directory)
            try:
                identity = identity_for(self.proc, target.pid)
                self.assertIsNotNone(identity)
                assert identity
                with patch.dict(
                    os.environ,
                    {
                        "XDG_DATA_HOME": str(root / "data"),
                        "XDG_CONFIG_HOME": str(config),
                    },
                ):
                    revealed = self.actions.perform(
                        "reveal",
                        identity,
                        {"workingDirectory": str(working_directory)},
                    )
                    self.assertTrue(revealed.ok, revealed.message)
                    self.assertTrue(
                        wait_until(marker.exists, timeout=5.0),
                        "xdg-open did not invoke the selected directory handler",
                    )
                opened = unquote(urlparse(marker.read_text(encoding="utf-8")).path)
                self.assertEqual(Path(opened), working_directory)
            finally:
                if target.poll() is None:
                    target.terminate()
                target.wait(timeout=3.0)
                self.assertTrue(
                    wait_until(lambda: self.runner.active_launchers() == 0),
                    "the XDG directory handler did not exit",
                )


if __name__ == "__main__":
    unittest.main()
