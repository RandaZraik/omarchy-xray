from pathlib import Path
from tempfile import TemporaryDirectory
import os
import pwd
import signal
import unittest
from unittest.mock import MagicMock, call, patch

from xray.actions.process_control import (
    ActionResult,
    ProcessActions,
    ProcessGuard,
    action_catalog,
)
from xray.config import TIMING
from xray.processes.identity import ProcessIdentity
from xray.system.procfs import ProcFs
from support.procfs import write_process


class ActionTests(unittest.TestCase):
    def test_catalog_uses_one_action_vocabulary(self) -> None:
        actions = action_catalog(
            has_window=True,
            has_working_directory=True,
            paused=False,
            controllable=True,
            can_relaunch=True,
        )
        self.assertEqual(
            [row["id"] for row in actions],
            ["focus", "reveal", "terminal", "pause", "terminate", "relaunch"],
        )
        self.assertTrue(
            next(row for row in actions if row["id"] == "terminate")["confirm"]
        )
        rootful = action_catalog(
            has_window=True,
            has_working_directory=True,
            paused=False,
            controllable=False,
            can_relaunch=True,
        )
        self.assertTrue(
            next(row for row in rootful if row["id"] == "relaunch")["available"]
        )
        self.assertFalse(
            next(row for row in rootful if row["id"] == "terminate")["available"]
        )
        unavailable = action_catalog(
            has_window=True,
            has_working_directory=True,
            paused=False,
            controllable=True,
            can_relaunch=False,
        )
        self.assertFalse(
            next(row for row in unavailable if row["id"] == "relaunch")["available"]
        )
        described = action_catalog(
            has_window=True,
            has_working_directory=True,
            paused=False,
            controllable=True,
            can_relaunch=True,
            confirmation_target="Chromium · PID 40",
            relaunch_target="container:abc",
        )
        self.assertEqual(
            next(row for row in described if row["id"] == "terminate")[
                "confirmationTarget"
            ],
            "Chromium · PID 40",
        )

    def test_every_action_revalidates_identity_before_dispatch(self) -> None:
        actions = ProcessActions(ProcFs(Path("/missing")), MagicMock())
        actions.guard.validate = MagicMock(return_value=(False, "stale"))
        identity = ProcessIdentity(40, 11, os.getuid())
        for action in (
            "focus",
            "reveal",
            "terminal",
            "pause",
            "resume",
            "terminate",
        ):
            self.assertEqual(actions.perform(action, identity, {}).message, "stale")
        self.assertEqual(actions.guard.validate.call_count, 6)

    def test_desktop_actions_use_argv_without_a_shell(self) -> None:
        runner = MagicMock()
        runner.run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, json=MagicMock(return_value={"address": "0xabc"})),
        ]
        runner.launch.return_value.returncode = 0
        actions = ProcessActions(ProcFs(Path("/missing")), runner)
        actions.guard.validate = MagicMock(return_value=(True, ""))
        identity = ProcessIdentity(40, 11, os.getuid())
        with (
            TemporaryDirectory() as directory,
            patch(
                "xray.actions.process_control.revalidate_window",
                return_value=({"address": "0xabc", "pid": 40}, "0xabc", ""),
            ),
        ):
            context = {
                "workingDirectory": directory,
                "window": {"address": "0xabc", "pid": 40},
            }
            self.assertTrue(actions.perform("focus", identity, context).ok)
            self.assertTrue(actions.perform("reveal", identity, context).ok)
            self.assertTrue(actions.perform("terminal", identity, context).ok)
            self.assertEqual(
                runner.run.call_args_list[0],
                call(
                    [
                        "hyprctl",
                        "dispatch",
                        'hl.dsp.focus({ window = "address:0xabc" })',
                    ]
                ),
            )
            self.assertEqual(
                runner.launch.call_args_list,
                [
                    call(["xdg-open", directory]),
                    call(
                        [
                            "xdg-terminal-exec",
                            f"--dir={directory}",
                            "--",
                            pwd.getpwuid(os.getuid()).pw_shell,
                        ],
                        cwd=directory,
                    ),
                ],
            )

    def test_focus_falls_back_for_older_hyprland_and_rejects_invalid_selectors(
        self,
    ) -> None:
        runner = MagicMock()
        runner.run.side_effect = [
            MagicMock(returncode=1),
            MagicMock(returncode=0),
            MagicMock(returncode=0, json=MagicMock(return_value={"address": "0xabc"})),
        ]
        actions = ProcessActions(ProcFs(Path("/missing")), runner)
        with patch(
            "xray.actions.process_control.revalidate_window",
            return_value=({"address": "0xabc", "pid": 40}, "0xabc", ""),
        ):
            result = actions._focus({"window": {"address": "0xabc", "pid": 40}})
        self.assertTrue(result.ok)
        self.assertEqual(
            runner.run.call_args_list[-2].args[0],
            [
                "hyprctl",
                "dispatch",
                "focuswindow",
                "address:0xabc",
            ],
        )

        runner.reset_mock()
        rejected = actions._focus(
            {"window": {"address": '0x1" }); os.execute("bad")', "pid": 40}}
        )
        self.assertFalse(rejected.ok)
        runner.run.assert_not_called()

    def test_focus_rejects_a_successful_dispatch_that_did_not_focus_the_window(
        self,
    ) -> None:
        runner = MagicMock()
        runner.run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, json=MagicMock(return_value={"address": "0x1"})),
            MagicMock(returncode=0),
            MagicMock(returncode=0, json=MagicMock(return_value={"address": "0x1"})),
        ]
        with (
            patch(
                "xray.system.hyprland.time.monotonic", side_effect=[0.0, 1.0, 0.0, 1.0]
            ),
            patch(
                "xray.actions.process_control.revalidate_window",
                return_value=(
                    {"address": "0xdeadbeef", "pid": 40},
                    "0xdeadbeef",
                    "",
                ),
            ),
        ):
            result = ProcessActions(ProcFs(Path("/missing")), runner)._focus(
                {"window": {"address": "0xdeadbeef", "pid": 40}}
            )
        self.assertFalse(result.ok)

    def test_focus_waits_for_hyprlands_asynchronous_dispatch(self) -> None:
        runner = MagicMock()
        runner.run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, json=MagicMock(return_value={"address": "0x1"})),
            MagicMock(
                returncode=0,
                json=MagicMock(return_value={"address": "0xdeadbeef"}),
            ),
        ]
        with (
            patch(
                "xray.system.hyprland.time.monotonic",
                side_effect=[0.0, 0.1, 0.2],
            ),
            patch("xray.system.hyprland.time.sleep"),
            patch(
                "xray.actions.process_control.revalidate_window",
                return_value=(
                    {"address": "0xdeadbeef", "pid": 40},
                    "0xdeadbeef",
                    "",
                ),
            ),
        ):
            result = ProcessActions(ProcFs(Path("/missing")), runner)._focus(
                {"window": {"address": "0xdeadbeef", "pid": 40}}
            )
        self.assertTrue(result.ok)
        self.assertEqual(runner.run.call_count, 3)

    def test_focus_rejects_a_reused_window_address_owned_by_another_pid(self) -> None:
        runner = MagicMock()
        with patch(
            "xray.actions.process_control.revalidate_window",
            return_value=(
                {},
                "0xabc",
                "The selected window is no longer available",
            ),
        ):
            result = ProcessActions(ProcFs(Path("/missing")), runner)._focus(
                {"window": {"address": "0xabc", "pid": 40}}
            )
        self.assertFalse(result.ok)
        runner.run.assert_not_called()

    def test_process_signals_and_relaunch_routes(self) -> None:
        actions = ProcessActions(ProcFs(Path("/missing")), MagicMock())
        actions.guard.validate = MagicMock(return_value=(True, ""))
        actions.guard.signal = MagicMock(return_value=ActionResult(True, "sent"))
        identity = ProcessIdentity(40, 11, os.getuid())
        with patch.object(
            actions, "_relaunch", return_value=ActionResult(True, "relaunched")
        ) as relaunch:
            for action in ("pause", "resume", "terminate"):
                self.assertTrue(actions.perform(action, identity, {}).ok)
            self.assertTrue(actions.perform("relaunch", identity, {}).ok)
            relaunch.assert_called_once()
        self.assertEqual(
            actions.perform("unknown", identity, {}).message, "Unknown action"
        )

    def test_signal_uses_a_pidfd_to_close_the_pid_reuse_race(self) -> None:
        actions = ProcessActions(ProcFs(Path("/missing")), MagicMock())
        actions.guard.validate = MagicMock(return_value=(True, ""))
        identity = ProcessIdentity(40, 11, os.getuid())
        with (
            patch("xray.actions.process_control.os.pidfd_open", return_value=7),
            patch("xray.actions.process_control.signal.pidfd_send_signal") as send,
            patch("xray.actions.process_control.os.close") as close,
            patch("xray.actions.process_control.os.kill") as kill,
        ):
            result = actions.guard.signal(identity, signal.SIGTERM)
        self.assertTrue(result.ok)
        send.assert_called_once_with(7, signal.SIGTERM)
        close.assert_called_once_with(7)
        kill.assert_not_called()

    def test_relaunch_delegates_only_to_a_proven_manager(self) -> None:
        runner = MagicMock()
        runner.run.return_value.returncode = 0
        actions = ProcessActions(ProcFs(Path("/missing")), runner)
        actions.guard.validate = MagicMock(return_value=(True, ""))
        identity = ProcessIdentity(40, 11, os.getuid())

        unmanaged = actions.perform("relaunch", identity, {"workingDirectory": "/tmp"})
        self.assertFalse(unmanaged.ok)
        runner.run.assert_not_called()

        service = actions.perform(
            "relaunch",
            identity,
            {"service": {"id": "demo.service", "scope": "user"}},
        )
        self.assertTrue(service.ok)
        self.assertEqual(service.reinspect_query, "service:user:demo.service")
        runner.run.assert_called_once_with(
            ["systemctl", "--user", "restart", "--", "demo.service"],
            timeout_seconds=TIMING.manager_restart_seconds,
        )

        runner.reset_mock()
        actions.guard.validate = MagicMock(return_value=(False, "different uid"))
        container = actions.perform(
            "relaunch",
            identity,
            {"container": {"id": "abc123", "runtime": "podman"}},
        )
        self.assertTrue(container.ok)
        actions.guard.validate.assert_not_called()
        self.assertEqual(container.reinspect_query, "container:podman:abc123")
        runner.run.assert_called_once_with(
            ["podman", "restart", "--", "abc123"],
            timeout_seconds=TIMING.manager_restart_seconds,
        )

        runner.reset_mock()
        injected = actions.perform(
            "relaunch",
            identity,
            {"container": {"id": "--latest", "runtime": "docker"}},
        )
        self.assertFalse(injected.ok)
        runner.run.assert_not_called()

    def test_guard_rejects_recycled_pid_and_other_user(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch("xray.actions.process_control.os.getuid", return_value=1000),
            patch("xray.actions.process_control.os.getpid", return_value=500),
        ):
            root = Path(directory)
            self._write(root, 500, 1, 1, 1000)
            self._write(root, 40, 1, 12, 1000)
            guard = ProcessGuard(ProcFs(root))
            self.assertFalse(guard.validate(ProcessIdentity(40, 11, 1000))[0])
            self._write(root, 41, 1, 13, 1001)
            self.assertFalse(guard.validate(ProcessIdentity(41, 13, 1001))[0])

    def test_guard_protects_its_ancestor_chain(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch("xray.actions.process_control.os.getuid", return_value=1000),
            patch("xray.actions.process_control.os.getpid", return_value=500),
        ):
            root = Path(directory)
            self._write(root, 500, 400, 1, 1000)
            self._write(root, 400, 1, 2, 1000)
            guard = ProcessGuard(ProcFs(root))
            self.assertFalse(guard.validate(ProcessIdentity(400, 2, 1000))[0])

    def _write(self, root: Path, pid: int, ppid: int, start: int, uid: int) -> None:
        write_process(root, pid, "demo", ppid, start=start, uid=uid)


if __name__ == "__main__":
    unittest.main()
