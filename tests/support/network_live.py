from __future__ import annotations

import json
import socket
import subprocess
import sys

from support.paths import PROJECT_ROOT


class TcpFixture:
    def __init__(self, ipv6: bool = False) -> None:
        family = socket.AF_INET6 if ipv6 else socket.AF_INET
        self.listener = socket.socket(family, socket.SOCK_STREAM)
        self.listener.settimeout(5)
        self.listener.bind(("::1" if ipv6 else "127.0.0.1", 0))
        self.listener.listen()
        self.port = self.listener.getsockname()[1]
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(PROJECT_ROOT / "tests/fixtures/network_fixture.py"),
                "6" if ipv6 else "4",
                str(self.port),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.peer, _address = self.listener.accept()
        self.peer.settimeout(5)
        ready = json.loads(self.process.stdout.readline())
        self.local_port = ready["localPort"]

    def transfer(self, direction: str, size: int) -> None:
        self.process.stdin.write(
            json.dumps({"direction": direction, "bytes": size}) + "\n"
        )
        self.process.stdin.flush()
        remaining = size
        while remaining:
            if direction == "send":
                data = self.peer.recv(min(remaining, 65536))
                if not data or data != b"x" * len(data):
                    raise AssertionError("Transfer did not match the fixture payload")
                remaining -= len(data)
            else:
                data = b"x" * min(remaining, 65536)
                self.peer.sendall(data)
                remaining -= len(data)
        completed = json.loads(self.process.stdout.readline())
        if completed != {"direction": direction, "bytes": size}:
            raise AssertionError(completed)

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=5)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            if pipe:
                pipe.close()
        self.peer.close()
        self.listener.close()

    def __enter__(self) -> TcpFixture:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
