from __future__ import annotations

from collections import OrderedDict
import time
from typing import Hashable


class RuntimeDetailsCache:
    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._values: OrderedDict[Hashable, tuple[float, dict[str, object]]] = (
            OrderedDict()
        )

    def clear(self) -> None:
        self._values.clear()

    def prune(self, now: float | None = None) -> None:
        observed_at = time.monotonic() if now is None else now
        expired = [
            key
            for key, (stored_at, _value) in self._values.items()
            if observed_at - stored_at >= self.ttl_seconds
        ]
        for key in expired:
            self._values.pop(key, None)

    def get(
        self, key: Hashable, now: float | None = None
    ) -> tuple[bool, dict[str, object]]:
        observed_at = time.monotonic() if now is None else now
        self.prune(observed_at)
        cached = self._values.get(key)
        if cached is None:
            return False, {}
        self._values.move_to_end(key)
        return True, dict(cached[1])

    def put(
        self,
        key: Hashable,
        value: dict[str, object],
        now: float | None = None,
    ) -> None:
        observed_at = time.monotonic() if now is None else now
        self.prune(observed_at)
        self._values[key] = (observed_at, dict(value))
        self._values.move_to_end(key)
        while len(self._values) > self.max_entries:
            self._values.popitem(last=False)

    def __len__(self) -> int:
        return len(self._values)
