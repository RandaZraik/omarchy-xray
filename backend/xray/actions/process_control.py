from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import pwd
import re
import signal

from xray.config import LIMITS, TIMING
from xray.processes.identity import ProcessIdentity, identity_for, parse_stat
from xray.runtime.containers import SUPPORTED_CONTAINER_RUNTIMES
from xray.runtime.context import revalidate_window
from xray.system.commands import CommandRunner
from xray.system.hyprland import focus_window
from xray.system.procfs import ProcFs


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    reinspect_query: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "message": self.message}


@dataclass(frozen=True)
class ActionDefinition:
    label: str
    icon: str
    requirement: str = ""
    confirm: bool = False


ACTION_DEFINITIONS = {
    "focus": ActionDefinition("Focus window", "focus", "window"),
    "reveal": ActionDefinition("Reveal files", "folder", "cwd"),
    "terminal": ActionDefinition("Open terminal here", "terminal", "cwd"),
    "pause": ActionDefinition("Pause process", "pause"),
    "resume": ActionDefinition("Resume process", "play"),
    "terminate": ActionDefinition("Terminate process", "stop", confirm=True),
    "relaunch": ActionDefinition(
        "Restart managed target",
        "restart",
        "relaunch",
        confirm=True,
    ),
}

_SAFE_MANAGER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,255}")


@dataclass(frozen=True)
class RelaunchPlan:
    command: list[str]
    message: str
    query: str


def relaunch_plan(context: dict[str, object]) -> RelaunchPlan | None:
    container = context.get("container", {})
    if isinstance(container, dict):
        runtime = str(container.get("runtime", ""))
        identifier = str(container.get("id", ""))
        if runtime in SUPPORTED_CONTAINER_RUNTIMES and _SAFE_MANAGER_ID.fullmatch(
            identifier
        ):
            return RelaunchPlan(
                [runtime, "restart", "--", identifier],
                "Container restarted",
                f"container:{runtime}:{identifier}",
            )

    service = context.get("service", {})
    if isinstance(service, dict):
        unit = str(service.get("id", ""))
        if (
            service.get("scope") == "user"
            and unit.endswith(".service")
            and _SAFE_MANAGER_ID.fullmatch(unit)
        ):
            return RelaunchPlan(
                ["systemctl", "--user", "restart", "--", unit],
                "User service restarted",
                f"service:user:{unit}",
            )
    return None


class ProcessGuard:
    """Revalidates a process immediately before a same-user signal."""

    def __init__(self, proc: ProcFs) -> None:
        self.proc = proc
        self.uid = os.getuid()
        self.protected_pids = self._ancestor_pids(os.getpid())

    def _ancestor_pids(self, pid: int) -> set[int]:
        protected: set[int] = {1, os.getpid()}
        current = pid
        for _ in range(LIMITS.ancestry_depth):
            if current <= 1 or (current in protected and current != pid):
                break
            protected.add(current)
            stat = self.proc.read(current, "stat")
            if not stat.available:
                break
            try:
                current = int(parse_stat(stat.value)["ppid"])
            except (TypeError, ValueError):
                break
        return protected

    def validate(self, expected: ProcessIdentity) -> tuple[bool, str]:
        current = identity_for(self.proc, expected.pid)
        if not current:
            return False, "The process is no longer running"
        if current != expected:
            return False, "The PID now belongs to a different process"
        if current.uid != self.uid:
            return False, "X-Ray only controls processes owned by your user"
        if current.pid in self.protected_pids:
            return False, "X-Ray will not control its shell or ancestor processes"
        return True, ""

    def signal(self, expected: ProcessIdentity, number: signal.Signals) -> ActionResult:
        try:
            pidfd = os.pidfd_open(expected.pid)
        except ProcessLookupError:
            return ActionResult(False, "The process ended before it could be signaled")
        except OSError as error:
            return ActionResult(False, f"The process could not be secured: {error}")
        valid, reason = self.validate(expected)
        if not valid:
            os.close(pidfd)
            return ActionResult(False, reason)
        try:
            signal.pidfd_send_signal(pidfd, number)
        except ProcessLookupError:
            return ActionResult(False, "The process ended before the signal was sent")
        except PermissionError:
            return ActionResult(
                False, "Permission was denied while signaling the process"
            )
        except OSError as error:
            return ActionResult(False, str(error))
        finally:
            os.close(pidfd)
        return ActionResult(
            True,
            {
                signal.SIGSTOP: "Process paused",
                signal.SIGCONT: "Process resumed",
                signal.SIGTERM: "Termination requested",
            }.get(number, "Signal sent"),
        )


def action_catalog(
    *,
    has_window: bool,
    has_working_directory: bool,
    paused: bool,
    controllable: bool,
    can_relaunch: bool,
    confirmation_target: str = "",
    relaunch_target: str = "",
) -> list[dict[str, object]]:
    ids = [
        "focus",
        "reveal",
        "terminal",
        "resume" if paused else "pause",
        "terminate",
        "relaunch",
    ]
    requirements = {
        "window": has_window,
        "cwd": has_working_directory,
        "relaunch": can_relaunch,
    }
    result = [
        {
            "id": action_id,
            "label": ACTION_DEFINITIONS[action_id].label,
            "icon": ACTION_DEFINITIONS[action_id].icon,
            "available": (
                can_relaunch
                if action_id == "relaunch"
                else controllable
                and requirements.get(ACTION_DEFINITIONS[action_id].requirement, True)
            ),
            "confirm": ACTION_DEFINITIONS[action_id].confirm,
            "confirmationTarget": (
                relaunch_target if action_id == "relaunch" else confirmation_target
            )
            if ACTION_DEFINITIONS[action_id].confirm
            else "",
        }
        for action_id in ids
    ]
    return result


class ProcessActions:
    def __init__(self, proc: ProcFs, runner: CommandRunner) -> None:
        self.proc = proc
        self.runner = runner
        self.guard = ProcessGuard(proc)

    def perform(
        self,
        action: str,
        identity: ProcessIdentity,
        context: dict[str, object],
    ) -> ActionResult:
        definition = ACTION_DEFINITIONS.get(action)
        if not definition:
            return ActionResult(False, "Unknown action")
        if action == "relaunch":
            return self._perform_relaunch(identity, context)
        valid, reason = self.guard.validate(identity)
        if not valid:
            return ActionResult(False, reason)
        handler = {
            "focus": self._perform_focus,
            "reveal": self._perform_reveal,
            "terminal": self._perform_terminal,
            "pause": self._perform_pause,
            "resume": self._perform_resume,
            "terminate": self._perform_terminate,
        }.get(action)
        if not handler:
            return ActionResult(False, "Unknown action")
        return handler(identity, context)

    def catalog(
        self,
        identity: ProcessIdentity,
        context: dict[str, object],
        *,
        paused: bool,
        confirmation_target: str,
    ) -> list[dict[str, object]]:
        controllable, _reason = self.guard.validate(identity)
        plan = relaunch_plan(context)
        return action_catalog(
            has_window=bool(context.get("window")),
            has_working_directory=bool(context.get("workingDirectory")),
            paused=paused,
            controllable=controllable,
            can_relaunch=plan is not None,
            confirmation_target=confirmation_target,
            relaunch_target=plan.query if plan else "",
        )

    def _perform_focus(
        self, identity: ProcessIdentity, context: dict[str, object]
    ) -> ActionResult:
        return self._focus(context)

    def _perform_reveal(
        self, identity: ProcessIdentity, context: dict[str, object]
    ) -> ActionResult:
        return self._launch(
            ["xdg-open", str(context.get("workingDirectory", ""))], context
        )

    def _perform_terminal(
        self, identity: ProcessIdentity, context: dict[str, object]
    ) -> ActionResult:
        return self._terminal(context)

    def _perform_pause(
        self, identity: ProcessIdentity, context: dict[str, object]
    ) -> ActionResult:
        return self.guard.signal(identity, signal.SIGSTOP)

    def _perform_resume(
        self, identity: ProcessIdentity, context: dict[str, object]
    ) -> ActionResult:
        return self.guard.signal(identity, signal.SIGCONT)

    def _perform_terminate(
        self, identity: ProcessIdentity, context: dict[str, object]
    ) -> ActionResult:
        return self.guard.signal(identity, signal.SIGTERM)

    def _perform_relaunch(
        self, identity: ProcessIdentity, context: dict[str, object]
    ) -> ActionResult:
        return self._relaunch(context)

    def _focus(self, context: dict[str, object]) -> ActionResult:
        window = (
            context.get("window") if isinstance(context.get("window"), dict) else {}
        )
        _current, address, error = revalidate_window(self.runner, window)
        if not address:
            return ActionResult(False, "No window is associated with this process")
        if error:
            return ActionResult(False, error)
        focused = focus_window(self.runner, address)
        return ActionResult(
            focused,
            "Window focused" if focused else "Hyprland could not focus the window",
        )

    def _launch(self, argv: list[str], context: dict[str, object]) -> ActionResult:
        path = str(context.get("workingDirectory", ""))
        if not path or not Path(path).is_dir():
            return ActionResult(False, "The working directory is unavailable")
        result = self.runner.launch(argv)
        if result.returncode != 0:
            return ActionResult(False, result.stderr)
        return ActionResult(True, "Opened")

    def _terminal(self, context: dict[str, object]) -> ActionResult:
        path = str(context.get("workingDirectory", ""))
        if not path or not Path(path).is_dir():
            return ActionResult(False, "The working directory is unavailable")
        login_shell = Path(pwd.getpwuid(os.getuid()).pw_shell)
        shell = (
            str(login_shell)
            if login_shell.is_absolute()
            and login_shell.is_file()
            and os.access(login_shell, os.X_OK)
            else "/bin/sh"
        )
        result = self.runner.launch(
            ["xdg-terminal-exec", f"--dir={path}", "--", shell], cwd=path
        )
        if result.returncode != 0:
            return ActionResult(False, result.stderr)
        return ActionResult(True, "Terminal opened")

    def _relaunch(
        self,
        context: dict[str, object],
    ) -> ActionResult:
        plan = relaunch_plan(context)
        if not plan:
            return ActionResult(
                False,
                "Relaunch is available only when a user service or container manager owns the target",
            )
        result = self.runner.run(
            plan.command, timeout_seconds=TIMING.manager_restart_seconds
        )
        if result.returncode != 0:
            return ActionResult(
                False, result.stderr or "The manager could not restart it"
            )
        return ActionResult(True, plan.message, plan.query)
