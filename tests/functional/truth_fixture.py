from __future__ import annotations

import ctypes
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time


def detach_from_terminal_tree() -> None:
    first_child = os.fork()
    if first_child > 0:
        raise SystemExit(0)
    os.setsid()
    second_child = os.fork()
    if second_child > 0:
        raise SystemExit(0)


def set_process_name(name: str) -> None:
    libc = ctypes.CDLL(None)
    libc.prctl(15, name.encode("utf-8"), 0, 0, 0)


def accept_connections(listener: socket.socket, clients: list[socket.socket]) -> None:
    while True:
        try:
            client, _ = listener.accept()
        except OSError:
            return
        clients.append(client)


def generate_known_activity(path: Path, stopped: threading.Event) -> None:
    block = b"x" * 4096
    with path.open("wb", buffering=0) as output:
        while not stopped.is_set():
            deadline = time.perf_counter() + 0.025
            value = 1
            while time.perf_counter() < deadline:
                value = (value * 33 + 17) % 1_000_003
            output.write(block)
            os.fsync(output.fileno())
            time.sleep(0.025)


def main() -> int:
    if len(sys.argv) < 2:
        return 2

    if os.environ.get("XRAY_TRUTH_FOREGROUND") != "1":
        detach_from_terminal_tree()

    locked_path = Path(sys.argv[1]).resolve()
    locked_file = locked_path.open("w+")
    locked_file.write("known X-Ray fixture\n")
    locked_file.flush()
    fcntl.flock(locked_file, fcntl.LOCK_EX)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    clients: list[socket.socket] = []
    threading.Thread(
        target=accept_connections, args=(listener, clients), daemon=True
    ).start()

    child = subprocess.Popen(["sleep", "300"])
    stopped = threading.Event()
    activity_path = locked_path.with_suffix(".activity")
    threading.Thread(
        target=generate_known_activity,
        args=(activity_path, stopped),
        daemon=True,
    ).start()
    set_process_name("xray-truth")
    print(
        json.dumps(
            {
                "pid": os.getpid(),
                "childPid": child.pid,
                "port": listener.getsockname()[1],
                "path": str(locked_path),
                "cwd": str(Path.cwd()),
                "activityPath": str(activity_path),
            }
        ),
        flush=True,
    )

    def stop(_number: int, _frame: object) -> None:
        stopped.set()
        child.terminate()
        listener.close()
        for client in clients:
            client.close()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signal.pause()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
