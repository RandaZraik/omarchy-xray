from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from xray.config import STATE_DIRECTORY, normalize_settings


MAX_SETTINGS_BYTES = 64 * 1024


class SessionSettings:
    """Typed access to the normalized settings used during an inspection."""

    def __init__(self, values: dict[str, object]) -> None:
        self._values = dict(values)

    @property
    def history_seconds(self) -> int:
        return int(self._values["historySeconds"])

    @property
    def capture_preview(self) -> bool:
        return bool(self._values["capturePreview"])

    def as_dict(self) -> dict[str, object]:
        return dict(self._values)


def default_state_home() -> Path:
    configured = os.environ.get("XDG_STATE_HOME")
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "state"
    )


class SettingsRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_home() / STATE_DIRECTORY / "settings.json"

    def load(self) -> dict[str, object]:
        try:
            with self.path.open("rb") as handle:
                raw = handle.read(MAX_SETTINGS_BYTES + 1)
            if len(raw) > MAX_SETTINGS_BYTES:
                return normalize_settings({})
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, TypeError, RecursionError):
            payload = {}
        return normalize_settings(payload)

    def save(self, values: object) -> dict[str, object]:
        normalized = normalize_settings(values)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        payload = (json.dumps(normalized, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)
        return normalized
