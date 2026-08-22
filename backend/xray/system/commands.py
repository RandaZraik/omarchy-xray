from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
import json
import os
import selectors
import signal
import shutil
import subprocess
import threading
import time
from typing import Mapping, Sequence

from xray.config import LIMITS


def _output_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    unavailable: bool = False
    timed_out: bool = False
    output_limited: bool = False

    def json_payload(self) -> tuple[object, bool]:
        if self.returncode != 0 or not self.stdout.strip():
            return None, False
        try:
            return json.loads(self.stdout), True
        except (ValueError, RecursionError):
            return None, False

    def json(self, fallback: object) -> object:
        payload, valid = self.json_payload()
        return payload if valid else fallback


class CommandRunner:
    """Runs fixed argv commands without a shell or inherited stdin."""

    def __init__(self, timeout_seconds: float = 2.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._launched: list[subprocess.Popen[bytes]] = []
        self._launcher_lock = threading.Lock()
        self._launcher_changed = threading.Condition(self._launcher_lock)
        self._reaper_started = False

    def _reap_launchers(self) -> None:
        with self._launcher_lock:
            self._launched = [
                process for process in self._launched if process.poll() is None
            ]

    def _reaper_loop(self) -> None:
        while True:
            with self._launcher_changed:
                self._launched = [
                    process for process in self._launched if process.poll() is None
                ]
                self._launcher_changed.wait(timeout=0.25 if self._launched else None)

    def _ensure_reaper_locked(self) -> None:
        if self._reaper_started:
            return
        self._reaper_started = True
        threading.Thread(
            target=self._reaper_loop,
            name="xray-command-reaper",
            daemon=True,
        ).start()

    def active_launchers(self) -> int:
        self._reap_launchers()
        return len(self._launched)

    def available(self, executable: str) -> bool:
        return shutil.which(executable) is not None

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float | None = None,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        self._reap_launchers()
        normalized = tuple(str(value) for value in argv)
        if not normalized:
            return CommandResult(
                normalized, 127, "", "command unavailable", unavailable=True
            )

        command_env = None
        if env:
            command_env = os.environ.copy()
            command_env.update({str(key): str(value) for key, value in env.items()})
        try:
            process = subprocess.Popen(
                normalized,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=command_env,
                start_new_session=True,
            )
        except FileNotFoundError:
            return CommandResult(
                normalized, 127, "", "command unavailable", unavailable=True
            )
        except OSError as error:
            return CommandResult(normalized, 126, "", str(error), unavailable=True)
        return self._collect(
            process, normalized, timeout_seconds or self.timeout_seconds
        )

    @staticmethod
    def _stop(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            with suppress(OSError):
                process.kill()

    def _collect(
        self,
        process: subprocess.Popen[bytes],
        argv: tuple[str, ...],
        timeout_seconds: float,
    ) -> CommandResult:
        streams = {process.stdout: bytearray(), process.stderr: bytearray()}
        selector = selectors.DefaultSelector()
        for stream in streams:
            if stream is not None:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
        deadline = time.monotonic() + max(0.01, timeout_seconds)
        timed_out = False
        output_limited = False
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    self._stop(process)
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    stream = key.fileobj
                    try:
                        chunk = os.read(stream.fileno(), 65_536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        continue
                    used = sum(len(value) for value in streams.values())
                    available = LIMITS.command_output_bytes - used
                    if available > 0:
                        streams[stream].extend(chunk[:available])
                    if len(chunk) > available:
                        output_limited = True
                        self._stop(process)
                        break
                if output_limited:
                    break
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._stop(process)
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    timed_out = True
        finally:
            selector.close()
            for stream in streams:
                if stream is not None:
                    stream.close()

        stdout = _output_text(bytes(streams.get(process.stdout, b"")))
        stderr = _output_text(bytes(streams.get(process.stderr, b"")))
        if timed_out and not stderr:
            stderr = "command timed out"
        if output_limited and not stderr:
            stderr = "command output exceeded the safety limit"
        return CommandResult(
            argv,
            124
            if timed_out
            else 125
            if output_limited
            else int(process.returncode or 0),
            stdout,
            stderr,
            timed_out=timed_out,
            output_limited=output_limited,
        )

    def launch(self, argv: Sequence[str], *, cwd: str | None = None) -> CommandResult:
        self._reap_launchers()
        normalized = tuple(str(value) for value in argv)
        if not normalized:
            return CommandResult(
                normalized, 127, "", "command unavailable", unavailable=True
            )
        if self.active_launchers() >= LIMITS.active_launchers:
            return CommandResult(
                normalized,
                125,
                "",
                f"at most {LIMITS.active_launchers} launched applications may be tracked",
                output_limited=True,
            )
        try:
            process = subprocess.Popen(
                normalized,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            with self._launcher_changed:
                self._launched.append(process)
                self._ensure_reaper_locked()
                self._launcher_changed.notify()
        except FileNotFoundError:
            return CommandResult(
                normalized, 127, "", "command unavailable", unavailable=True
            )
        except OSError as error:
            return CommandResult(normalized, 126, "", str(error), unavailable=True)
        return CommandResult(normalized, 0, "", "")
