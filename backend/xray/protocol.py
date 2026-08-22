from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from xray.session import InspectionSession


@dataclass(frozen=True)
class ProtocolReply:
    payload: dict[str, object]
    stop: bool = False


class Protocol:
    def __init__(self, session: InspectionSession) -> None:
        self.session = session

    def handle(self, request: object) -> ProtocolReply:
        if not isinstance(request, dict):
            return ProtocolReply(
                {"id": "", "ok": False, "error": "request must be an object"}
            )
        raw_id = request.get("id", "")
        request_id = (
            str(raw_id)[:128] if isinstance(raw_id, (str, int, float, bool)) else ""
        )
        raw_command = request.get("command", "")
        command = raw_command if isinstance(raw_command, str) else ""
        try:
            data, stop = self._dispatch(command, request)
            return ProtocolReply({"id": request_id, "ok": True, "data": data}, stop)
        except (OSError, OverflowError, TypeError, ValueError, RecursionError) as error:
            return ProtocolReply(
                {"id": request_id, "ok": False, "error": str(error)[:1000]}
            )

    def _dispatch(
        self, command: str, request: dict[str, object]
    ) -> tuple[object, bool]:
        routes: dict[str, Callable[[], object]] = {
            "bootstrap": self.session.bootstrap,
            "inspectFocused": self.session.inspect_focused,
            "catalog": self.session.catalog,
            "inspect": lambda: self.session.inspect(request.get("query", "")),
            "refresh": lambda: self.session.refresh(request.get("compact") is True),
            "focusProcess": lambda: self.session.focus_process(request.get("pid")),
            "pickWindow": self.session.pick_window,
            "resetBaseline": self.session.reset_baseline,
            "configure": lambda: self.session.configure(request.get("settings")),
            "setSamplingPaused": lambda: self.session.set_sampling_paused(
                request.get("paused")
            ),
            "closeInspection": self.session.end_inspection,
            "action": lambda: self.session.perform_action(
                request.get("action"), request.get("inspectionId")
            ),
            "exportCapsule": lambda: self.session.export(request.get("directory")),
            "openCapsule": lambda: self.session.open_capsule(request.get("path")),
            "compareCapsule": lambda: self.session.compare_with_capsule(
                request.get("path")
            ),
            "report": self.session.report,
            "capturePreview": self.session.capture_preview,
        }
        if command == "shutdown":
            self.session.close()
            return {"closed": True}, True
        route = routes.get(command)
        if not route:
            raise ValueError("unknown command")
        return route(), False
