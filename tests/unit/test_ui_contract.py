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


def qml_blocks(document: str, type_name: str) -> list[str]:
    blocks: list[str] = []
    cursor = 0
    marker = re.compile(rf"\b{re.escape(type_name)}\s*\{{")
    while match := marker.search(document, cursor):
        start = document.find("{", match.start())
        depth = 0
        for index in range(start, len(document)):
            if document[index] == "{":
                depth += 1
            elif document[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(document[match.start() : index + 1])
                    cursor = index + 1
                    break
        else:
            raise AssertionError(f"Unclosed {type_name} block")
    return blocks


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
        cards += source("ui/views/ProcessConsole.qml")
        self.assertIn("function count(domain, snapshot)", domains)
        self.assertIn("function rows(domain, snapshot)", domains)
        self.assertEqual(cards.count("detailsCount: DetailDomains.count("), 7)

    def test_cards_delegate_long_lists_to_the_shared_drawer(self) -> None:
        cards = "\n".join(
            path.read_text() for path in (ROOT / "ui/cards").glob("*.qml")
        )
        self.assertNotIn("ListView", cards)
        self.assertIn("ScrollBar.vertical", source("ui/drawers/DetailDrawer.qml"))

    def test_process_drilldown_exposes_task_manager_and_xray_evidence(self) -> None:
        table = source("ui/views/ProcessEvidenceTable.qml")
        for field in (
            "PROCESS / COMMAND",
            "PID",
            "USER",
            "THREADS",
            "MEMORY",
            "CPU",
            "READ / WRITE",
        ):
            self.assertIn(field, table)
        self.assertIn('property string sortKey: "tree"', table)
        self.assertIn("ProcessEvidence.filter", table)
        self.assertIn("ProcessEvidence.sort", table)
        self.assertIn("ProcessEvidence.presentation", table)
        self.assertIn('objectName: "xraySelectedProcessCommand"', table)
        self.assertIn("text: root.selectedCommand", table)

    def test_detail_drawer_blocks_clicks_from_reaching_dashboard_cards(self) -> None:
        drawer = source("ui/drawers/DetailDrawer.qml")
        overlay = source("ui/XRayOverlay.qml")
        self.assertIn('objectName: "xrayDrawerInputBarrier"', drawer)
        self.assertIn("acceptedButtons: Qt.AllButtons", drawer)
        self.assertIn("preventStealing: true", drawer)
        self.assertIn("readonly property bool dashboardInteractive", overlay)
        self.assertGreaterEqual(overlay.count("enabled: root.dashboardInteractive"), 2)

    def test_outside_click_dismisses_overlay_without_inside_click_through(self) -> None:
        overlay = source("ui/XRayOverlay.qml")
        self.assertIn('objectName: "xrayBackdropDismissArea"', overlay)
        self.assertIn("onClicked: root.dismissTopLayer()", overlay)
        self.assertIn('objectName: "xrayDeskInputBarrier"', overlay)

    def test_all_custom_tap_targets_advertise_clickability(self) -> None:
        rendered = "\n".join(path.read_text() for path in sorted((ROOT / "ui").rglob("*.qml")))
        handlers = qml_blocks(rendered, "TapHandler")
        self.assertTrue(handlers)
        for handler in handlers:
            self.assertIn("cursorShape:", handler)
            self.assertIn("Qt.PointingHandCursor", handler)

    def test_clickable_hover_layers_own_the_visible_hand_cursor(self) -> None:
        rendered = "\n".join(path.read_text() for path in sorted((ROOT / "ui").rglob("*.qml")))
        handlers = qml_blocks(rendered, "HoverHandler")
        self.assertTrue(handlers)
        for handler in handlers:
            self.assertIn("cursorShape:", handler)
            self.assertIn("Qt.PointingHandCursor", handler)

    def test_clickable_dismissal_surfaces_advertise_clickability(self) -> None:
        overlay = source("ui/XRayOverlay.qml")
        confirmation = source("ui/views/ConfirmationOverlay.qml")
        self.assertRegex(
            overlay,
            r'objectName: "xrayBackdropDismissArea"[\s\S]*?'
            r"cursorShape: Qt\.PointingHandCursor[\s\S]*?"
            r"onClicked: root\.dismissTopLayer\(\)",
        )
        self.assertRegex(
            overlay,
            r"cursorShape: Qt\.PointingHandCursor\s+"
            r"onClicked: controller\.dismissDrawerAfterPointer\(\)",
        )
        self.assertRegex(
            confirmation,
            r"MouseArea\s*\{\s*anchors\.fill: parent\s+"
            r"cursorShape: Qt\.PointingHandCursor\s+"
            r"onClicked: root\.cancelled\(\)",
        )

    def test_every_evidence_drawer_uses_the_full_workspace_height(self) -> None:
        overlay = source("ui/XRayOverlay.qml")
        detail = overlay[overlay.index("DetailDrawer {") : overlay.index("SettingsDrawer {")]
        self.assertIn("anchors.top: parent.top", detail)
        self.assertIn("anchors.bottom: parent.bottom", detail)
        self.assertNotIn("Math.min(12, detailDrawer.rows.length)", detail)

    def test_grouped_drawers_use_collapsible_sections_without_zebra_rows(self) -> None:
        drawer = source("ui/drawers/DetailDrawer.qml")
        section = source("ui/controls/DrawerSectionHeader.qml")
        process = source("ui/views/ProcessConsole.qml")
        self.assertIn("function toggleSection(id)", drawer)
        self.assertIn("DelegateModel {", drawer)
        self.assertIn('filterOnGroup: "visible"', drawer)
        self.assertIn("collapsed: root.sectionCollapsed(parent.rowData.sectionId)", drawer)
        self.assertIn("onSectionToggled: function(sectionId)", drawer)
        self.assertIn("cursorShape: enabled ? Qt.PointingHandCursor", section)
        self.assertNotRegex(drawer, r"index\s*%\s*2")
        self.assertNotRegex(process, r"index\s*%\s*2")

    def test_process_table_empty_space_opens_the_complete_tree(self) -> None:
        process = source("ui/views/ProcessConsole.qml")
        card = source("ui/controls/Card.qml")
        self.assertIn("footer: Item", process)
        self.assertIn("id: emptyAreaHover", process)
        self.assertIn("externalHover: emptyAreaHovered", process)
        self.assertIn("onHoveredChanged: root.emptyAreaHovered = hovered", process)
        self.assertIn("onTapped: root.detailsRequested()", process)
        self.assertIn("root.theme.cardHoverOverlayOpacity", card)

    def test_catalog_items_are_indented_beneath_group_headers(self) -> None:
        browser = source("ui/views/TargetBrowser.qml")
        self.assertIn("anchors.leftMargin: root.theme.targetBrowserChildIndent", browser)
        self.assertIn(
            "targetBrowserChildIndent: pad * 2 + 1",
            source("ui/XRayTheme.qml"),
        )
        self.assertIn("anchors.left: targetRow.left", browser)

    def test_detail_drawer_live_patch_imports_domain_helper(self) -> None:
        controller = source("ui/controllers/XRayController.qml")
        self.assertIn('import "../DetailDomains.js" as DetailDomains', controller)
        self.assertIn("DetailDomains.patchTouches", controller)

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

    def test_identity_rail_keeps_live_history_beside_numeric_metrics(self) -> None:
        identity = source("ui/views/IdentityBar.qml")
        overlay = source("ui/XRayOverlay.qml")
        self.assertIn("TelemetryTrace", identity)
        self.assertIn("performanceSamples: controller.performanceSamples", overlay)
        self.assertIn("performanceWindowSeconds: controller.performanceWindowSeconds", overlay)

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
        self.assertIn(
            "target: ${{ needs.validate.outputs.target_sha }}", portable_tests
        )

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
