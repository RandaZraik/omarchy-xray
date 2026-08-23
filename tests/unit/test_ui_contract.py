from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


def source(path: str) -> str:
    return (ROOT / path).read_text()


def yaml_mapping_block(document: str, key: str, indent: int) -> str:
    lines = document.splitlines()
    header = " " * indent + key + ":"
    start = next(index for index, line in enumerate(lines) if line == header)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        line_indent = len(line) - len(line.lstrip())
        if line_indent <= indent:
            end = index
            break
    return "\n".join(lines[start:end])


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

    def test_release_validation_is_isolated_from_release_writes(self) -> None:
        workflow = source(".github/workflows/prepare-release.yml")
        jobs = yaml_mapping_block(workflow, "jobs", 0)
        validate = yaml_mapping_block(jobs, "validate", 2)
        portable_tests = yaml_mapping_block(jobs, "portable-tests", 2)
        draft = yaml_mapping_block(jobs, "draft", 2)

        self.assertRegex(workflow, r"(?m)^permissions: \{\}$")
        self.assertRegex(validate, r"(?m)^    permissions:\n      contents: read$")
        self.assertRegex(validate, r"actions/checkout@[0-9a-f]{40}(?:\s|$)")
        self.assertIn("persist-credentials: false", validate)
        self.assertNotIn("contents: write", validate)
        self.assertIn("fetch-depth: 0", validate)
        self.assertIn("git merge-base --is-ancestor HEAD origin/master", validate)

        self.assertRegex(
            portable_tests,
            r"(?m)^    permissions:\n      contents: read$",
        )
        self.assertIn("uses: ./.github/workflows/ci.yml", portable_tests)
        self.assertIn("target: ${{ needs.validate.outputs.target_sha }}", portable_tests)

        self.assertIn("needs: [validate, portable-tests]", draft)
        self.assertRegex(draft, r"(?m)^    permissions:\n      contents: write$")
        self.assertNotIn("actions/checkout@", draft)
        self.assertIn('ref="refs/tags/$TAG"', draft)
        self.assertIn('sha="$TARGET_SHA"', draft)
        self.assertIn("--verify-tag", draft)
        self.assertIn("trap cleanup_tag EXIT", draft)
        self.assertNotIn('--target "$TARGET_SHA"', draft)
        self.assertNotIn("inputs.target", draft)
        self.assertNotIn("pull_request_target", workflow)


if __name__ == "__main__":
    unittest.main()
