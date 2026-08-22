import unittest
from unittest.mock import patch
import sys
import subprocess
from types import SimpleNamespace

from xray.system.commands import CommandResult, CommandRunner


class CommandRunnerTests(unittest.TestCase):
    def test_missing_commands_are_reported_without_a_preflight_lookup(self) -> None:
        runner = CommandRunner()
        result = runner.run(["xray-command-that-does-not-exist"])
        self.assertEqual(result.returncode, 127)
        self.assertTrue(result.unavailable)

    def test_detached_launch_never_uses_a_shell(self) -> None:
        runner = CommandRunner()
        with patch("xray.system.commands.subprocess.Popen") as popen:
            result = runner.launch(["demo", "--safe"], cwd="/tmp")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(popen.call_args.args[0], ("demo", "--safe"))
        self.assertEqual(popen.call_args.kwargs["cwd"], "/tmp")
        self.assertNotIn("shell", popen.call_args.kwargs)

    def test_detached_launches_share_one_reaper_and_are_bounded(self) -> None:
        runner = CommandRunner()
        process = SimpleNamespace(poll=lambda: None)
        with (
            patch("xray.system.commands.subprocess.Popen", return_value=process),
            patch("xray.system.commands.threading.Thread") as thread,
            patch(
                "xray.system.commands.LIMITS",
                SimpleNamespace(active_launchers=1),
            ),
        ):
            first = runner.launch(["demo"])
            second = runner.launch(["another"])

        self.assertEqual(first.returncode, 0)
        self.assertEqual(second.returncode, 125)
        thread.assert_called_once()

    def test_timeout_output_is_always_safe_to_serialize(self) -> None:
        runner = CommandRunner()
        result = runner.run(
            [
                sys.executable,
                "-c",
                "import os,time; os.write(1, b'partial\\xff'); os.write(2, b'too slow'); time.sleep(3)",
            ],
            timeout_seconds=1.0,
        )
        self.assertTrue(result.timed_out)
        self.assertEqual(result.stdout, "partial�")
        self.assertEqual(result.stderr, "too slow")

    def test_json_payload_distinguishes_valid_empty_data_from_invalid_output(
        self,
    ) -> None:
        self.assertEqual(CommandResult((), 0, "[]", "").json_payload(), ([], True))
        self.assertEqual(
            CommandResult((), 0, "not-json", "").json_payload(), (None, False)
        )

    def test_json_payload_rejects_pathological_nesting(self) -> None:
        with patch("xray.system.commands.json.loads", side_effect=RecursionError):
            self.assertEqual(
                CommandResult((), 0, "[]", "").json_payload(), (None, False)
            )

    def test_output_is_bounded_before_a_helper_can_exhaust_memory(self) -> None:
        with patch(
            "xray.system.commands.LIMITS",
            SimpleNamespace(command_output_bytes=1024),
        ):
            result = CommandRunner().run(
                [sys.executable, "-c", "import os; os.write(1, b'x' * 4096)"]
            )
        self.assertTrue(result.output_limited)
        self.assertEqual(result.returncode, 125)
        self.assertEqual(len(result.stdout.encode()), 1024)

    def test_process_surviving_both_waits_returns_timeout_instead_of_crashing(
        self,
    ) -> None:
        process = SimpleNamespace(
            stdout=None,
            stderr=None,
            pid=999999,
            returncode=None,
            poll=lambda: None,
            kill=lambda: None,
        )

        def wait(timeout):
            raise subprocess.TimeoutExpired(("stuck",), timeout)

        process.wait = wait
        with patch("xray.system.commands.os.killpg", side_effect=ProcessLookupError):
            result = CommandRunner()._collect(process, ("stuck",), 1.0)

        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, 124)


if __name__ == "__main__":
    unittest.main()
