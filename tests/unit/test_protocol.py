import unittest

from xray.protocol import Protocol


class FakeResolver:
    def catalog(self):
        return {"windows": []}


class FakeSession:
    def __init__(self):
        self.resolver = FakeResolver()
        self.closed = False

    def bootstrap(self):
        return {"ready": True}

    def catalog(self):
        return self.resolver.catalog()

    def inspect_focused(self):
        return {"target": {"rootPid": 42}}

    def inspect(self, query):
        return {"query": query}

    def refresh(self, compact=False):
        return {"refreshed": True, "compact": compact}

    def focus_process(self, pid):
        return {"pid": pid}

    def pick_window(self):
        return {"cancelled": True}

    def reset_baseline(self):
        return {"reset": True}

    def configure(self, values):
        return values

    def set_sampling_paused(self, paused):
        if not isinstance(paused, bool):
            raise ValueError("paused must be a boolean")
        return {"paused": paused}

    def end_inspection(self):
        return {"closed": True}

    def perform_action(self, action, inspection_id):
        return {"action": action, "inspectionId": inspection_id}

    def export(self, directory):
        return {"directory": directory}

    def open_capsule(self, path):
        return {"opened": path}

    def compare_with_capsule(self, path):
        return {"compared": path}

    def report(self):
        return {"text": "report"}

    def capture_preview(self):
        return {"previewPath": "/tmp/preview.png"}

    def close(self):
        self.closed = True


class ProtocolTests(unittest.TestCase):
    def test_every_command_has_a_typed_reply(self) -> None:
        protocol = Protocol(FakeSession())
        cases = [
            ("bootstrap", {}),
            ("inspectFocused", {}),
            ("catalog", {}),
            ("inspect", {"query": ":80"}),
            ("refresh", {}),
            ("focusProcess", {"pid": 2}),
            ("pickWindow", {}),
            ("resetBaseline", {}),
            ("configure", {"settings": {}}),
            ("setSamplingPaused", {"paused": True}),
            ("closeInspection", {}),
            ("action", {"action": "focus", "inspectionId": 7}),
            ("exportCapsule", {"directory": "/tmp"}),
            ("openCapsule", {"path": "x"}),
            ("compareCapsule", {"path": "x"}),
            ("report", {}),
            ("capturePreview", {}),
        ]
        for index, (command, fields) in enumerate(cases):
            with self.subTest(command=command):
                reply = protocol.handle({"id": index, "command": command, **fields})
                self.assertTrue(reply.payload["ok"])
                self.assertFalse(reply.stop)

    def test_unknown_and_invalid_requests_fail_without_crashing(self) -> None:
        protocol = Protocol(FakeSession())
        self.assertFalse(protocol.handle([]).payload["ok"])
        self.assertFalse(protocol.handle({"id": "a", "command": "nope"}).payload["ok"])
        malformed = protocol.handle({"id": {"nested": True}, "command": []})
        self.assertFalse(malformed.payload["ok"])
        self.assertEqual(malformed.payload["id"], "")

    def test_compact_refresh_is_opt_in_for_the_live_ui(self) -> None:
        protocol = Protocol(FakeSession())

        full = protocol.handle({"command": "refresh"}).payload["data"]
        compact = protocol.handle({"command": "refresh", "compact": True}).payload[
            "data"
        ]

        self.assertFalse(full["compact"])
        self.assertTrue(compact["compact"])

    def test_sampling_state_requires_an_explicit_boolean(self) -> None:
        protocol = Protocol(FakeSession())

        for fields in ({}, {"paused": None}, {"paused": 1}, {"paused": "true"}):
            with self.subTest(fields=fields):
                reply = protocol.handle(
                    {"id": "pause", "command": "setSamplingPaused", **fields}
                )
                self.assertFalse(reply.payload["ok"])
                self.assertIn("boolean", reply.payload["error"])

    def test_shutdown_closes_session(self) -> None:
        session = FakeSession()
        reply = Protocol(session).handle({"id": "x", "command": "shutdown"})
        self.assertTrue(reply.stop)
        self.assertTrue(session.closed)


if __name__ == "__main__":
    unittest.main()
