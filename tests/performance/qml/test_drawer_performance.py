from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from support.quickshell import (
    DRAWER_ENVIRONMENT_KEYS,
    PROJECT_ROOT,
    QuickshellHarness,
)


HARNESS = QuickshellHarness()
ORACLE = Path(__file__).with_name("oracles") / "drawer_performance_oracle.qml"
SEARCH_ORACLE = PROJECT_ROOT / "tests/support/oracles/drawer_search_oracle.qml"


@unittest.skipUnless(
    HARNESS.available,
    "requires a live Omarchy Quickshell session",
)
class DrawerPerformanceTests(unittest.TestCase):
    def _measure(
        self,
        oracle: Path,
        marker_name: str,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, object]:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shell = HARNESS.stage_plugin(root, oracle)
            completed = HARNESS.run(
                shell,
                timeout=35,
                environment=extra_env,
                unset_environment=DRAWER_ENVIRONMENT_KEYS,
                state_home=root / "state",
            )
        self.assertEqual(completed.returncode, 0, completed.output)
        return completed.json_marker(marker_name)

    def _measure_toggle(self, extra_env: dict[str, str]) -> dict[str, object]:
        result = self._measure(ORACLE, "XRAY_DRAWER_PERF", extra_env)
        self.assertLess(result["collapseElapsedMs"], 250)
        self.assertLess(result["expandElapsedMs"], 250)
        return result

    def test_large_files_section_toggle(self) -> None:
        result = self._measure_toggle({"XRAY_DRAWER_DOMAIN": "files"})
        self.assertEqual(result["sourceCount"], 2500)
        self.assertEqual(result["resourceCount"], 1250)
        self.assertEqual(result["collapsedCount"], 1)
        self.assertEqual(result["expandedCount"], 1251)

    def test_runtime_software_section_toggle(self) -> None:
        result = self._measure_toggle(
            {
                "XRAY_DRAWER_DOMAIN": "runtime",
                "XRAY_DRAWER_SECTION": "software",
            }
        )
        self.assertEqual(result["domain"], "runtime")
        self.assertEqual(result["section"], "software")
        self.assertEqual(result["resourceCount"], 188)
        self.assertEqual(result["collapsedCount"], 11)
        self.assertEqual(result["expandedCount"], 192)

    def test_large_files_search_latency(self) -> None:
        result = self._measure(SEARCH_ORACLE, "XRAY_DRAWER_SEARCH")
        self.assertEqual(result["sourceCount"], 12000)
        self.assertEqual(result["filteredCount"], 2)
        self.assertEqual(result["restoredCount"], 3001)
        self.assertLess(result["searchElapsedMs"], 350)
        self.assertLess(result["clearElapsedMs"], 250)


if __name__ == "__main__":
    unittest.main()
