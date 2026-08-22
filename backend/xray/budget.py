from __future__ import annotations

import json


def encoded_json_size(value: object) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def bounded_json_rows(rows: list[object], budget: int) -> list[object]:
    retained: list[object] = []
    used = 2
    for row in rows:
        size = encoded_json_size(row) + 1
        if retained and used + size > budget:
            break
        retained.append(row)
        used += size
    return retained
