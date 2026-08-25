from __future__ import annotations

import json


def parse_json_marker(output: str, marker_name: str) -> dict[str, object]:
    prefix = f"{marker_name} "
    marker = next(
        (
            line.partition(prefix)[2]
            for line in output.splitlines()
            if prefix in line
        ),
        "",
    )
    if not marker:
        raise AssertionError(f"process returned no {marker_name} payload:\n{output}")
    return json.loads(marker)
