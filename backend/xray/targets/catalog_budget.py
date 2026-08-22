from __future__ import annotations

from xray.budget import bounded_json_rows, encoded_json_size
from xray.config import LIMITS


_DOMAINS = (
    "quickTargets",
    "windows",
    "processes",
    "devices",
    "gpu",
    "ports",
    "services",
    "containers",
)


def constrain_catalog(catalog: dict[str, object]) -> dict[str, object]:
    limited = list(catalog.get("limited", []))
    for domain in _DOMAINS:
        rows = catalog.get(domain)
        if not isinstance(rows, list):
            continue
        sanitized = [_bound_strings(row) for row in rows]
        if sanitized != rows:
            limited.append(f"{domain.title()} search text was bounded for safe display")
        retained = bounded_json_rows(sanitized, LIMITS.catalog_domain_bytes)
        if len(retained) != len(sanitized):
            limited.append(
                f"{domain.title()} search is limited to {len(retained)} of {len(sanitized)} entries by the catalog budget"
            )
        catalog[domain] = retained
    catalog["limited"] = list(dict.fromkeys(_bound_strings(limited)))
    while encoded_json_size(catalog) > LIMITS.catalog_bytes:
        candidates = [
            (len(rows), domain)
            for domain in _DOMAINS
            if isinstance((rows := catalog.get(domain)), list) and len(rows) > 1
        ]
        if not candidates:
            break
        _length, domain = max(candidates)
        rows = catalog[domain]
        catalog[domain] = rows[: max(1, len(rows) // 2)]
        catalog["limited"] = list(
            dict.fromkeys(
                [
                    *catalog["limited"],
                    f"{domain.title()} search was reduced further to fit the aggregate catalog budget",
                ]
            )
        )
    return catalog


def _bound_strings(value: object) -> object:
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) <= LIMITS.catalog_string_bytes:
            return value
        return (
            encoded[: LIMITS.catalog_string_bytes].decode("utf-8", errors="ignore")
            + "…"
        )
    if isinstance(value, list):
        return [_bound_strings(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _bound_strings(item) for key, item in value.items()}
    return value
