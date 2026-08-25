from __future__ import annotations

from pathlib import Path

import pytest


TEST_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Assign one execution tier from the test's directory."""
    for item in items:
        relative = Path(str(item.path)).relative_to(TEST_ROOT)
        parts = relative.parts
        if parts[0] in {"unit", "contract", "integration"}:
            tier = "portable"
        elif parts[:2] == ("system", "desktop"):
            tier = "desktop"
        elif parts[0] == "system":
            tier = "system"
        elif parts[0] == "performance":
            tier = "performance"
        else:
            raise pytest.UsageError(f"test has no execution tier: {relative}")
        item.add_marker(getattr(pytest.mark, tier))
