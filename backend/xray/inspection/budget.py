from __future__ import annotations

from xray.budget import bounded_json_rows, encoded_json_size
from xray.config import LIMITS


_DOMAIN_BUDGETS = (
    (("processes",), 3 * 1024 * 1024, "processes", "Process rows"),
    (("files",), 4 * 1024 * 1024, "files", "Open file rows"),
    (("connections",), 1024 * 1024, "connections", "Connection rows"),
    (("locks",), 512 * 1024, "files", "File lock rows"),
    (("logs",), 512 * 1024, "runtime", "Journal rows"),
    (("explanations",), 512 * 1024, "runtime", "Explanation rows"),
    (("timeline",), 512 * 1024, "runtime", "Timeline rows"),
    (("devices", "pipewire"), 512 * 1024, "pipewire", "PipeWire rows"),
    (("devices", "gpu"), 512 * 1024, "gpu", "GPU rows"),
    (("devices", "inhibitors"), 512 * 1024, "inhibitors", "Inhibitor rows"),
)


def constrain_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    """Bound high-volume evidence while preserving the target and root process."""
    if encoded_json_size(snapshot) <= LIMITS.snapshot_bytes:
        return snapshot
    for path, budget, domain, label in _DOMAIN_BUDGETS:
        rows = _rows_at(snapshot, path)
        if rows is None:
            continue
        retained = bounded_json_rows(rows, budget)
        if len(retained) == len(rows):
            continue
        _set_rows(snapshot, path, retained)
        _mark_limited(
            snapshot,
            domain,
            f"{label} are limited to {len(retained)} of {len(rows)} entries by the snapshot budget",
        )

    while encoded_json_size(snapshot) > LIMITS.snapshot_bytes:
        candidates = [
            (len(rows), path, domain, label)
            for path, _budget, domain, label in _DOMAIN_BUDGETS
            if (rows := _rows_at(snapshot, path)) and len(rows) > 1
        ]
        if not candidates:
            break
        _length, path, domain, label = max(candidates, key=lambda item: item[0])
        rows = _rows_at(snapshot, path) or []
        retained = rows[: max(1, len(rows) // 2)]
        _set_rows(snapshot, path, retained)
        _mark_limited(
            snapshot,
            domain,
            f"{label} were reduced further to fit the aggregate snapshot budget",
        )
    return snapshot


def _rows_at(snapshot: dict[str, object], path: tuple[str, ...]) -> list[object] | None:
    current: object = snapshot
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, list) else None


def _set_rows(
    snapshot: dict[str, object], path: tuple[str, ...], rows: list[object]
) -> None:
    current: dict[str, object] = snapshot
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = rows


def _mark_limited(snapshot: dict[str, object], domain: str, message: str) -> None:
    coverage = snapshot.get("coverage")
    if not isinstance(coverage, dict):
        return
    limited = coverage.get("limited")
    values = list(limited) if isinstance(limited, list) else []
    if message not in values:
        values.append(message)
    coverage["limited"] = values
    coverage["statusCode"] = "limited"
    coverage["status"] = "Some data unavailable"
    domains = coverage.get("domains")
    if isinstance(domains, dict):
        domains[domain] = "limited"
        if domain in {"pipewire", "gpu", "inhibitors"}:
            domains["devices"] = "limited"
