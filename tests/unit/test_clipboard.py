import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from xray.system.clipboard import read_clipboard
from xray.system.commands import CommandResult
from xray.config import LIMITS, TIMING


def process_running(pid):
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return False
    return state not in ("Z", "X")


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        timeout = shutil.which("timeout")
        if not timeout:
            self.skipTest("requires GNU coreutils timeout")
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "timeout").symlink_to(timeout)
        self.environment = patch.dict(os.environ, {"PATH": str(self.root)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def provider(self, body):
        path = self.root / "wl-paste"
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o700)

    def test_normal_unicode_paste_and_primary_selection(self):
        self.provider(
            "import sys\n"
            "assert sys.argv[1:4] == ['--no-newline', '--type', 'text']\n"
            "print('primary' if '--primary' in sys.argv else 'مرحبا 🌍', end='')\n"
        )
        self.assertEqual(read_clipboard(), {"text": "مرحبا 🌍"})
        self.assertEqual(read_clipboard(primary=True), {"text": "primary"})

    def test_byte_limit_accepts_exact_limit_and_rejects_overflow(self):
        for count in (LIMITS.clipboard_bytes, LIMITS.clipboard_bytes + 1):
            with self.subTest(count=count):
                self.provider(f"import os\nos.write(1, b'x' * {count})\n")
                result = read_clipboard()
                if count == LIMITS.clipboard_bytes:
                    self.assertEqual(result, {"text": "x" * count})
                else:
                    self.assertEqual(set(result), {"error"})
                    self.assertIn("too large", result["error"])

    def test_stdout_and_stderr_share_one_byte_budget(self):
        self.provider(
            "import os\nos.write(1, b'x' * 12000)\nos.write(2, b'e' * 12000)\n"
        )
        self.assertIn("too large", read_clipboard()["error"])

    def test_trickling_clipboard_cannot_extend_the_deadline(self):
        marker = self.root / "pid"
        self.provider(
            "import os,time\n"
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text(str(os.getpid()))\n"
            "while True:\n"
            "    os.write(1, b'x')\n"
            "    time.sleep(0.02)\n"
        )
        started = time.monotonic()
        self.assertIn("did not respond", read_clipboard()["error"])
        self.assertLess(time.monotonic() - started, 4.5)
        reader_pid = int(marker.read_text())
        deadline = time.monotonic() + 1
        while process_running(reader_pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(process_running(reader_pid))

    def test_watchdog_stops_reader_after_python_helper_is_killed(self):
        marker = self.root / "pid"
        self.provider(
            "import os,time\n"
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text(str(os.getpid()))\n"
            "time.sleep(60)\n"
        )
        helper = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[2] / "backend/main.py"),
                "--paste-clipboard",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        reader_fd = None
        try:
            deadline = time.monotonic() + 3
            while not marker.exists() or not marker.read_text():
                self.assertLess(
                    time.monotonic(), deadline, "clipboard reader did not start"
                )
                self.assertIsNone(
                    helper.poll(), "clipboard helper exited before reading"
                )
                time.sleep(0.01)
            reader_pid = int(marker.read_text())
            reader_fd = os.pidfd_open(reader_pid)
            helper.kill()
            helper.wait(timeout=1)
            deadline = time.monotonic() + TIMING.clipboard_seconds + 2
            while process_running(reader_pid) and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(
                process_running(reader_pid), "reader outlived its independent watchdog"
            )
        finally:
            if helper.poll() is None:
                helper.kill()
            helper.wait(timeout=1)
            if reader_fd is not None:
                try:
                    signal.pidfd_send_signal(reader_fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                finally:
                    os.close(reader_fd)

    def test_watchdog_exit_statuses_report_a_timeout(self):
        for returncode in (124, -signal.SIGKILL, 128 + signal.SIGKILL):
            with (
                self.subTest(returncode=returncode),
                patch(
                    "xray.system.clipboard.CommandRunner.run",
                    return_value=CommandResult((), returncode, "", ""),
                ),
            ):
                self.assertIn("did not respond", read_clipboard()["error"])

    def test_missing_timeout_reports_the_required_dependency(self):
        (self.root / "timeout").unlink()
        self.provider("pass\n")
        self.assertIn("coreutils", read_clipboard()["error"])

    def test_empty_binary_missing_and_failed_clipboards(self):
        self.assertIn("wl-clipboard", read_clipboard()["error"])
        self.provider("pass\n")
        self.assertEqual(read_clipboard(), {"text": ""})
        (self.root / "wl-paste").chmod(0o600)
        self.assertIn("wl-clipboard", read_clipboard()["error"])
        self.provider("import sys\nsys.stderr.write('foreign error')\nsys.exit(1)\n")
        self.assertEqual(read_clipboard(), {"error": "No clipboard text available."})
        self.provider("import os\nos.write(1, b'valid\\xff')\n")
        self.assertEqual(read_clipboard(), {"text": "valid�"})

    def test_helper_returns_one_json_frame_without_interpreting_text(self):
        content = '$(touch /tmp/never)\n"quoted"\tمرحبا'
        self.provider(f"import sys\nsys.stdout.write({content!r})\n")
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[2] / "backend/main.py"),
                "--paste-clipboard",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        self.assertEqual(completed.stderr, "")
        self.assertEqual(len(completed.stdout.splitlines()), 1)
        self.assertEqual(json.loads(completed.stdout), {"text": content})
