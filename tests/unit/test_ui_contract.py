from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


def source(path: str) -> str:
    return (ROOT / path).read_text()


class UiContractTests(unittest.TestCase):
    """Static checks for security and cross-component invariants.

    Interactive behavior belongs to the real QML runtime oracles rather than
    brittle assertions about implementation text.
    """

    def test_plain_text_is_the_only_rendered_text_primitive(self) -> None:
        self.assertIn("textFormat: Text.PlainText", source("ui/controls/PlainText.qml"))
        rendered = "\n".join(
            path.read_text()
            for path in [
                ROOT / "BarWidget.qml",
                *sorted((ROOT / "ui").rglob("*.qml")),
            ]
            if path.name != "PlainText.qml"
        )
        self.assertNotRegex(rendered, r"\bText\s*\{")

    def test_card_counts_and_drawers_share_domain_definitions(self) -> None:
        domains = source("ui/DetailDomains.js")
        cards = "\n".join(
            path.read_text() for path in (ROOT / "ui/cards").glob("*.qml")
        )
        self.assertIn("function count(domain, snapshot)", domains)
        self.assertIn("function rows(domain, snapshot)", domains)
        self.assertEqual(cards.count("detailsCount: DetailDomains.count("), 7)

    def test_cards_delegate_long_lists_to_the_shared_drawer(self) -> None:
        cards = "\n".join(
            path.read_text() for path in (ROOT / "ui/cards").glob("*.qml")
        )
        self.assertNotIn("ListView", cards)
        self.assertIn("ScrollBar.vertical", source("ui/drawers/DetailDrawer.qml"))

    def test_open_overlay_is_pinned_to_its_original_monitor(self) -> None:
        overlay = source("ui/XRayOverlay.qml")
        self.assertIn("inspectionScreen = focusedScreen()", overlay)
        self.assertIn("screen: root.inspectionScreen || root.focusedScreen()", overlay)
        self.assertIn("onClosed: root.inspectionScreen = null", overlay)

    def test_capsule_summary_includes_every_compared_domain_and_metric(self) -> None:
        comparison = source("ui/controllers/XRayCapsules.qml")
        for field in (
            "domains.devices",
            "domains.runtime",
            "cpuPercent",
            "memoryBytes",
            "gpuPercent",
        ):
            self.assertIn(field, comparison)

    def test_settings_ui_is_generated_from_the_backend_contract(self) -> None:
        drawer = source("ui/drawers/SettingsDrawer.qml")
        editor = source("ui/controls/SettingEditor.qml")
        self.assertIn("model: root.schema", drawer)
        self.assertNotIn('setting("refreshSeconds")', drawer)
        self.assertIn('root.settingData.type === "choice"', editor)
        self.assertIn('root.settingData.type === "boolean"', editor)

    def test_typography_and_colors_come_from_the_shared_theme(self) -> None:
        theme_path = ROOT / "ui/XRayTheme.qml"
        theme = theme_path.read_text()
        qml_paths = [
            ROOT / "BarWidget.qml",
            *sorted((ROOT / "ui").rglob("*.qml")),
        ]
        components = "\n".join(
            path.read_text() for path in qml_paths if path != theme_path
        )

        for token in (
            "microFontSize",
            "captionFontSize",
            "bodyFontSize",
            "labelFontSize",
            "summaryFontSize",
            "sectionFontSize",
            "metricFontSize",
            "heroFontSize",
        ):
            self.assertIn(token, theme)
        self.assertIsNone(re.search(r"font\.pixelSize:\s*\d", components))
        self.assertIsNone(re.search(r"fontSize:\s*\d", components))
        self.assertNotRegex(components, r"#[0-9a-fA-F]{3,8}")
        self.assertNotIn('color: "transparent"', components)
        self.assertNotIn("Qt.rgba(", components)
        self.assertNotIn("Color.", components)
        self.assertNotIn("Style.", components)
        self.assertNotRegex(components, r"border\.width:\s*\d")

    def test_ci_is_read_only_and_checks_out_an_immutable_revision(self) -> None:
        workflow = source(".github/workflows/ci.yml")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertRegex(workflow, r"actions/checkout@[0-9a-f]{40}")
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertNotIn("contents: write", workflow)

    def test_ci_executes_the_portable_qml_behavior_oracle(self) -> None:
        workflow = source(".github/workflows/ci.yml")
        self.assertIn("qml-qt6", workflow)
        self.assertIn("test_qml_logic.py", workflow)


if __name__ == "__main__":
    unittest.main()
