import json
import unittest

from xray.config import LIMITS
from xray.inspection.budget import constrain_snapshot
from xray.targets.catalog_budget import constrain_catalog


class EvidenceBudgetTests(unittest.TestCase):
    def test_snapshot_budget_preserves_root_and_marks_truncated_domains(self) -> None:
        payload = "x" * 300_000
        snapshot = {
            "target": {"rootPid": 41},
            "processes": [
                {"pid": 41, "name": "root", "command": [payload]},
                *(
                    {"pid": 42 + index, "name": "child", "command": [payload]}
                    for index in range(55)
                ),
            ],
            "files": [{"target": payload} for _ in range(20)],
            "connections": [],
            "locks": [],
            "logs": [],
            "explanations": [],
            "timeline": [],
            "devices": {"pipewire": [], "gpu": [], "inhibitors": []},
            "coverage": {
                "statusCode": "full",
                "status": "All data available",
                "limited": [],
                "domains": {"processes": "available", "files": "available"},
            },
        }

        constrained = constrain_snapshot(snapshot)

        size = len(json.dumps(constrained, separators=(",", ":")).encode())
        self.assertLessEqual(size, LIMITS.snapshot_bytes)
        self.assertEqual(constrained["processes"][0]["pid"], 41)
        self.assertLess(len(constrained["processes"]), 56)
        self.assertEqual(constrained["coverage"]["statusCode"], "limited")
        self.assertEqual(constrained["coverage"]["domains"]["processes"], "limited")
        self.assertEqual(constrained["coverage"]["domains"]["files"], "limited")

    def test_catalog_budget_bounds_every_string_and_aggregate_payload(self) -> None:
        oversized = "resource-" + "x" * (LIMITS.catalog_string_bytes + 100)
        catalog = {
            "windows": [{"title": oversized} for _ in range(500)],
            "processes": [{"name": oversized} for _ in range(500)],
            "devices": [],
            "gpu": [],
            "ports": [],
            "services": [],
            "containers": [],
            "limited": [],
        }

        constrained = constrain_catalog(catalog)

        size = len(json.dumps(constrained, separators=(",", ":")).encode())
        self.assertLessEqual(size, LIMITS.catalog_bytes)
        for domain in ("windows", "processes"):
            for row in constrained[domain]:
                value = next(iter(row.values()))
                self.assertLessEqual(
                    len(value.encode()), LIMITS.catalog_string_bytes + len("…".encode())
                )
        self.assertTrue(any("bounded" in message for message in constrained["limited"]))


if __name__ == "__main__":
    unittest.main()
