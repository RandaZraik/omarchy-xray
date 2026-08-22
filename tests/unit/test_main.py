from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from unittest.mock import patch

from main import MAX_REQUEST_BYTES, emit, read_request
from xray.config import LIMITS
from xray.system.procfs import ProcFs


class RequestReaderTests(unittest.TestCase):
    def test_oversized_response_is_replaced_with_a_bounded_error(self) -> None:
        from io import StringIO

        output = StringIO()
        with patch("main.sys.stdout", output):
            emit({"id": "request-7", "ok": True, "data": "x" * LIMITS.response_bytes})

        reply = json.loads(output.getvalue())
        self.assertEqual(reply["id"], "request-7")
        self.assertFalse(reply["ok"])
        self.assertIn("safety limit", reply["error"])

    def test_discards_one_oversized_frame_and_recovers(self) -> None:
        valid = b'{"id":"ok","command":"bootstrap"}\n'
        stream = BytesIO(b"x" * (MAX_REQUEST_BYTES + 8) + b"\n" + valid)

        self.assertEqual(read_request(stream), (b"", True))
        self.assertEqual(read_request(stream), (valid, False))
        self.assertIsNone(read_request(stream))

    def test_non_utf8_linux_paths_are_safe_for_backend_json(self) -> None:
        with TemporaryDirectory() as directory:
            link = Path(directory) / "link"
            os.symlink(b"/tmp/invalid-\xff", os.fsencode(link))
            value = ProcFs(Path(directory)).readlink("link").value
            encoded = json.dumps({"path": value}, ensure_ascii=False).encode("utf-8")

        self.assertIn(b"invalid-", encoded)
        self.assertNotIn("\udcff", value)


if __name__ == "__main__":
    unittest.main()
