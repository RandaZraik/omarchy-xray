from __future__ import annotations

import json
import sys

from xray.config import LIMITS
from xray.protocol import Protocol
from xray.session import InspectionSession


MAX_REQUEST_BYTES = 1_048_576


def emit(payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > LIMITS.response_bytes:
        encoded = json.dumps(
            {
                "id": payload.get("id", ""),
                "ok": False,
                "error": "response exceeds the safety limit",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    sys.stdout.write(encoded + "\n")
    sys.stdout.flush()


def read_request(stream: object) -> tuple[bytes, bool] | None:
    raw = stream.readline(MAX_REQUEST_BYTES + 1)
    if not raw:
        return None
    if len(raw) <= MAX_REQUEST_BYTES:
        return raw, False
    while raw and not raw.endswith(b"\n"):
        raw = stream.readline(MAX_REQUEST_BYTES + 1)
    return b"", True


def main() -> int:
    session = InspectionSession()
    protocol = Protocol(session)
    try:
        stream = sys.stdin.buffer
        while item := read_request(stream):
            raw, oversized = item
            if oversized:
                emit({"id": "", "ok": False, "error": "request exceeds the size limit"})
                continue
            try:
                request = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                emit({"id": "", "ok": False, "error": "request is not valid JSON"})
                continue
            reply = protocol.handle(request)
            emit(reply.payload)
            if reply.stop:
                break
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
