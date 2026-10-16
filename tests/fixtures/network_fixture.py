"""A long-lived client with explicit application-byte accounting for live tests."""
import json
import os
import socket
import sys


family = socket.AF_INET6 if sys.argv[1] == "6" else socket.AF_INET
with socket.socket(family, socket.SOCK_STREAM) as client:
    client.connect(("::1" if family == socket.AF_INET6 else "127.0.0.1", int(sys.argv[2])))
    print(json.dumps({"pid": os.getpid(), "localPort": client.getsockname()[1]}), flush=True)
    for line in sys.stdin:
        command = json.loads(line)
        remaining = int(command["bytes"])
        if command["direction"] == "send":
            while remaining:
                data = b"x" * min(remaining, 65536)
                client.sendall(data)
                remaining -= len(data)
        else:
            while remaining:
                data = client.recv(min(remaining, 65536))
                if not data or data != b"x" * len(data):
                    raise RuntimeError("Transfer did not match the fixture payload")
                remaining -= len(data)
        print(json.dumps({"bytes": command["bytes"], "direction": command["direction"]}), flush=True)
