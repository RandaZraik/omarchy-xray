from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class LiveBackend:
    def __init__(self, state_home: Path) -> None:
        environment = dict(os.environ)
        environment["XDG_STATE_HOME"] = str(state_home)
        self.process = subprocess.Popen(
            [sys.executable, "backend/main.py"],
            cwd=PROJECT_ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._next_id = 0

    def __enter__(self) -> LiveBackend:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def request(
        self, command: str, timeout: float = 12.0, **fields: object
    ) -> dict[str, object]:
        self._next_id += 1
        request_id = f"truth-{self._next_id}"
        return self.raw(
            json.dumps({"id": request_id, "command": command, **fields}),
            timeout,
            request_id,
        )

    def raw(
        self, line: str, timeout: float = 12.0, expected_id: str = ""
    ) -> dict[str, object]:
        if not self.process.stdin or not self.process.stdout:
            raise AssertionError("backend pipes are unavailable")
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        events = selector.select(timeout)
        selector.close()
        if not events:
            raise AssertionError(
                f"backend timed out handling a request: {self._stderr()}"
            )
        line = self.process.stdout.readline()
        if not line:
            raise AssertionError(f"backend exited handling a request: {self._stderr()}")
        response = json.loads(line)
        if response.get("id") != expected_id:
            raise AssertionError(f"unexpected backend reply: {response}")
        return response

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.request("shutdown", timeout=3.0)
            except (AssertionError, BrokenPipeError, OSError):
                self.process.terminate()
        try:
            self.process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3.0)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream:
                try:
                    stream.close()
                except (BrokenPipeError, OSError):
                    pass

    def _stderr(self) -> str:
        if not self.process.stderr or self.process.poll() is None:
            return ""
        return self.process.stderr.read()[-4000:]


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False
