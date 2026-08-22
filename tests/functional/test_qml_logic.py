from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


QML = shutil.which("qml6") or shutil.which("qml")
ORACLE = Path(__file__).with_name("qml_logic_oracle.qml")


@unittest.skipUnless(QML, "requires a Qt QML runtime")
class QmlLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            [str(QML), "-platform", "offscreen", str(ORACLE)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            env={
                **os.environ,
                "QT_FORCE_STDERR_LOGGING": "1",
                "QT_LOGGING_TO_CONSOLE": "1",
            },
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr or completed.stdout)
        output = completed.stdout + "\n" + completed.stderr
        marker = next(
            (
                line.partition("XRAY_QML ")[2]
                for line in output.splitlines()
                if "XRAY_QML " in line
            ),
            "",
        )
        if not marker:
            raise AssertionError(f"QML oracle returned no payload: {output}")
        cls.data = json.loads(marker)

    def test_device_states_are_consistent(self) -> None:
        self.assertTrue(all(not row["active"] for row in self.data["empty"]["rows"]))
        self.assertEqual(sum(row["active"] for row in self.data["active"]["rows"]), 4)
        self.assertEqual(len(self.data["active"]["activeRows"]), 4)
        self.assertEqual(self.data["mixed"]["rows"][1]["meta"], "2 LIVE")

    def test_device_overflow_and_limited_sources_are_explicit(self) -> None:
        self.assertEqual(self.data["overflow"]["rows"][0]["meta"], "3 LIVE")
        self.assertEqual(
            self.data["limited"]["limitedSources"],
            ["pipewire", "gpu", "inhibitors"],
        )
        self.assertEqual(self.data["limited"]["rows"][0]["meta"], "UNAVAILABLE")
        self.assertEqual(self.data["limited"]["rows"][6]["meta"], "PARTIAL")
        self.assertEqual(self.data["limited"]["rows"][7]["meta"], "UNAVAILABLE")
        self.assertEqual(self.data["limited"]["activeRows"], [])

    def test_every_search_catalog_domain_returns_an_actionable_query(self) -> None:
        expected = {
            "windowSearch": "window:0xa",
            "serviceSearch": "service:user:demo.service",
            "containerSearch": "container:docker:abcdef",
            "deviceSearch": "pid:12",
            "gpuSearch": "pid:13",
            "portSearch": ":5173",
        }
        for name, query in expected.items():
            with self.subTest(name=name):
                self.assertTrue(self.data[name])
                self.assertEqual(self.data[name][0]["query"], query)
                if name != "windowSearch":
                    self.assertEqual(len(self.data[name]), 1)
        self.assertEqual(self.data["boundedSearch"], [])

    def test_network_endpoints_are_unambiguous(self) -> None:
        self.assertEqual(self.data["ipv4Endpoint"], "127.0.0.1:443")
        self.assertEqual(self.data["ipv6Endpoint"], "[2001:db8::1]:443")

    def test_every_detail_domain_exposes_its_complete_rows(self) -> None:
        self.assertEqual(self.data["detailCounts"], self.data["detailRowCounts"])
        self.assertEqual(
            self.data["detailCounts"],
            {
                "processes": 1,
                "connections": 1,
                "files": 2,
                "devices": 5,
                "runtime": 20,
                "cause": 1,
                "explanations": 4,
                "coverage": 2,
                "alternatives": 2,
            },
        )
        runtime_titles = {row["title"] for row in self.data["runtimeRows"]}
        self.assertIn("demo.service", runtime_titles)
        self.assertIn("demo", runtime_titles)
        self.assertIn("Identity", runtime_titles)
        self.assertIn("AppArmor / LSM", runtime_titles)
        self.assertIn("Out-of-memory priority", runtime_titles)
        self.assertIn("Package", runtime_titles)
        self.assertIn("Git project", runtime_titles)
        self.assertIn("Unit state", runtime_titles)
        self.assertIn("Namespace · mnt", runtime_titles)
        self.assertIn("Limit · open files", runtime_titles)
        self.assertIn("libc.so", runtime_titles)
        self.assertIn("ready", runtime_titles)

    def test_explanation_drawer_keeps_claim_proof_next_step_and_timeline(self) -> None:
        rows = self.data["explanationRows"]
        self.assertEqual(
            [row["title"] for row in rows],
            ["Listener", "Source", "Next check", "Socket opened"],
        )


if __name__ == "__main__":
    unittest.main()
