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

    def test_device_drawer_rows_keep_type_icons_and_prioritize_activity(self) -> None:
        rows = self.data["deviceDetailRows"]
        self.assertTrue(rows)
        self.assertTrue(all(row.get("icon") for row in rows))
        active = [row["active"] for row in rows]
        self.assertEqual(active, sorted(active, reverse=True))
        self.assertEqual(rows[0]["icon"], "microphone")

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
            "gpuFallbackLabelSearch": "pid:14",
            "portSearch": ":5173",
        }
        for name, query in expected.items():
            with self.subTest(name=name):
                self.assertTrue(self.data[name])
                self.assertEqual(self.data[name][0]["query"], query)
                if name != "windowSearch":
                    self.assertEqual(len(self.data[name]), 1)
        self.assertEqual(self.data["boundedSearch"], [])
        self.assertEqual(self.data["exactPortSearch"][0]["query"], ":5173")

    def test_target_browser_groups_and_owner_choices_are_complete(self) -> None:
        self.assertEqual(
            [row["kind"] for row in self.data["windowOnlySearch"]], ["window"]
        )
        self.assertEqual(
            [row["kind"] for row in self.data["processOnlySearch"]], ["process"]
        )
        self.assertEqual(self.data["browseKinds"][:2], ["quick", "window"])
        self.assertEqual(set(self.data["browseKinds"][2:4]), {"device", "gpu"})
        self.assertEqual(
            self.data["browseKinds"][4:],
            ["port", "container", "service", "process"],
        )
        self.assertEqual(self.data["filters"][0]["id"], "all")
        self.assertEqual(self.data["filters"][0]["label"], "ALL")
        self.assertEqual(self.data["targetCount"], 7)
        self.assertEqual(self.data["shortcutCount"], 1)
        self.assertEqual(self.data["partitionCount"], self.data["targetCount"])
        self.assertEqual(self.data["completeSearchCount"], 100)
        self.assertEqual(
            len(self.data["browseKinds"]),
            self.data["targetCount"] + self.data["shortcutCount"],
        )
        self.assertEqual(len(self.data["portBrowse"]), 1)
        self.assertEqual(self.data["portBrowse"][0]["query"], ":5173")
        self.assertEqual(
            [row["query"] for row in self.data["ownerMatches"]],
            ["pid:10", "pid:11"],
        )
        self.assertTrue(self.data["ownerMatches"][0]["selected"])

    def test_network_endpoints_are_unambiguous(self) -> None:
        self.assertEqual(self.data["ipv4Endpoint"], "127.0.0.1:443")
        self.assertEqual(self.data["ipv6Endpoint"], "[2001:db8::1]:443")
        self.assertEqual(self.data["defaultMemory"], "621.6 MiB")

    def test_compact_device_badges_remain_visually_distinct(self) -> None:
        self.assertNotIn("•", self.data["deviceIcons"])
        self.assertEqual(len(set(self.data["deviceIcons"])), 4)

    def test_detail_rows_keep_low_level_connection_and_descriptor_evidence(self) -> None:
        connection = self.data["connectionRows"][0]
        self.assertEqual(connection["pids"], [10])
        self.assertEqual(connection["inode"], 77)
        self.assertEqual(connection["networkNamespace"], "net:[1]")
        self.assertEqual(connection["remote"], "10.0.0.2:443")

        descriptor, lock = self.data["fileRows"]
        self.assertEqual(descriptor["position"], 12)
        self.assertEqual(descriptor["flags"], "0100002")
        self.assertEqual(descriptor["mountId"], 29)
        self.assertEqual(lock["start"], "0")
        self.assertEqual(lock["end"], "EOF")
        self.assertEqual(lock["scope"], "ADVISORY")

    def test_every_detail_domain_exposes_its_complete_rows(self) -> None:
        self.assertEqual(self.data["detailCounts"], self.data["detailRowCounts"])
        self.assertEqual(
            self.data["detailCounts"],
            {
                "processes": 1,
                "connections": 1,
                "files": 2,
                "devices": 5,
                "runtime": 19,
                "cause": 1,
                "explanations": 2,
                "coverage": 2,
                "alternatives": 2,
            },
        )
        runtime_titles = {row["title"] for row in self.data["runtimeRows"]}
        self.assertIn("demo.service", runtime_titles)
        self.assertIn("demo", runtime_titles)
        self.assertIn("Process identity", runtime_titles)
        self.assertIn("AppArmor / LSM", runtime_titles)
        self.assertIn("Out-of-memory priority", runtime_titles)
        self.assertIn("Package", runtime_titles)
        self.assertIn("Git project", runtime_titles)
        self.assertIn("Unit state", runtime_titles)
        self.assertIn("Mount namespace", runtime_titles)
        self.assertIn("open files", runtime_titles)
        self.assertIn("libc.so", runtime_titles)
        self.assertIn("ready", runtime_titles)
        runtime_sections = {row["section"] for row in self.data["runtimeRows"]}
        self.assertEqual(
            runtime_sections,
            {
                "workload",
                "isolation",
                "namespaces",
                "resources",
                "software",
                "container",
                "journal",
            },
        )

    def test_grouped_presentation_preserves_data_and_unfiltered_totals(self) -> None:
        presentation = self.data["connectionPresentation"]
        self.assertEqual(presentation[0]["rowType"], "section")
        self.assertEqual(presentation[0]["sectionId"], "active")
        self.assertEqual(presentation[0]["count"], 1)
        self.assertEqual(presentation[1]["remote"], "10.0.0.2:443")

        fallback = self.data["unknownSectionPresentation"]
        self.assertEqual(fallback[0]["sectionId"], "active")
        self.assertEqual(fallback[1]["title"], "Future evidence")

        self.assertEqual(
            self.data["fileSummary"],
            [
                {"label": "DESCRIPTORS", "value": "1"},
                {"label": "RESOURCES", "value": "1"},
                {"label": "LOCKS", "value": "1"},
                {"label": "DELETED", "value": "0", "tone": "danger"},
            ],
        )

    def test_large_file_section_toggles_reuse_prepared_groups(self) -> None:
        result = self.data["largeFilePresentation"]
        self.assertEqual(result["sourceCount"], 2500)
        self.assertEqual(result["resourceCount"], 1250)
        self.assertEqual(result["flatCount"], 1251)
        self.assertEqual(
            result["sectionCountLabel"],
            "1250 resources  ·  2500 descriptors",
        )
        self.assertEqual(result["expandedCount"], 1251)
        self.assertEqual(result["collapsedCount"], 1)
        self.assertTrue(result["rowIdentityPreserved"])
        self.assertLess(result["prepareElapsedMs"], 1000)
        self.assertLess(result["toggleElapsedMs"], 250)

    def test_explanation_drawer_keeps_claim_proof_next_step_and_timeline(self) -> None:
        rows = self.data["explanationRows"]
        self.assertEqual(
            [row["title"] for row in rows],
            ["Listener", "Socket opened"],
        )
        self.assertEqual(rows[0]["rowType"], "finding")
        self.assertEqual(rows[0]["evidence"], ["socket inode 7"])
        self.assertEqual(rows[0]["nextStep"], "Inspect owner")
        self.assertEqual(rows[1]["rowType"], "timeline")

    def test_process_evidence_filters_sorts_and_summarizes_real_fields(self) -> None:
        self.assertEqual(self.data["processUserFilter"], [10, 11])
        self.assertEqual(self.data["processPidFilter"], [11])
        self.assertEqual(self.data["processNameFilter"], [11])
        self.assertEqual(self.data["processCommandFilter"], [11])
        self.assertEqual(self.data["processFallbackUidFilter"], [12])
        self.assertEqual(self.data["processNonBtopFieldFilter"], [])
        self.assertEqual(self.data["processCpuSort"], [11, 10, 12])
        self.assertEqual(self.data["processCommandSort"], [12, 10, 11])
        self.assertEqual(self.data["processTreeOrder"], [10, 11, 12])
        self.assertEqual(
            self.data["processSummary"],
            {"processes": 3, "threads": 9, "memoryBytes": 7168},
        )
        self.assertEqual(self.data["processFallbackUser"], "UID 4242")
        self.assertEqual(self.data["processState"], "running")
        self.assertEqual(self.data["processCommand"], "root --safe")
        self.assertEqual(
            self.data["processConciseCommand"], "adw dashboard --port 9000"
        )
        self.assertEqual(self.data["processCommandLauncher"], "via python3")
        self.assertEqual(
            self.data["embeddedArgvConciseCommand"],
            "chromium --load-extension=/usr/share/omarchy/extensions/"
            "whatsapp-slim --oauth2-client-id=demo",
        )
        self.assertEqual(
            self.data["variantStyleProcessCommand"],
            "/workspace/.venv/bin/python3 /workspace/.venv/bin/adw "
            "dashboard --port 9000",
        )


if __name__ == "__main__":
    unittest.main()
