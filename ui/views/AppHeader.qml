import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui
import "../controls"
import "../Format.js" as Format

Item {
    id: root

    required property var theme
    property var catalog: ({})
    property var capabilities: ({})
    property var snapshot: ({})
    property bool offline: false
    property bool interactionEnabled: true
    property alias queryText: searchField.text
    property alias paletteVisible: targetPalette.visible

    signal searchAccepted(string query)
    signal pickRequested()
    signal pauseRequested()
    signal capsuleRequested()
    signal settingsRequested()
    signal closeRequested()
    signal catalogRequested()

    z: targetPalette.visible ? 30 : 0
    Layout.fillWidth: true
    Layout.preferredHeight: 46
    Layout.minimumHeight: 46
    Layout.maximumHeight: 46

    function focusSearch(selectAll) {
        root.catalogRequested();
        searchField.forceActiveFocus();
        targetPalette.visible = true;
        if (selectAll) searchField.selectAll();
    }

    RowLayout {
            id: headerRow
            anchors.fill: parent
            spacing: root.theme.gap

            RowLayout {
                id: brandGroup
                Layout.preferredWidth: implicitWidth
                Layout.minimumWidth: implicitWidth
                spacing: root.theme.gap

                PlainText {
                    text: Format.icon("xray")
                    color: root.theme.accent
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.heroFontSize
                    renderType: Text.NativeRendering
                }
                ColumnLayout {
                    spacing: 0
                    PlainText {
                        text: "X—RAY"
                        color: root.theme.sectionText
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.sectionFontSize
                        font.bold: true
                        font.letterSpacing: root.theme.brandTracking
                    }
                    PlainText {
                        text: "TRACE · CONTEXT · CONTROL"
                        color: root.theme.accent
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
                        font.letterSpacing: root.theme.taglineTracking
                    }
                }
            }

            Item {
                id: searchContainer
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                Layout.minimumHeight: 38
                Layout.maximumHeight: 38

                Ui.TextField {
                    id: searchField
                    objectName: "xraySearchField"
                    anchors.fill: parent
                    enabled: root.interactionEnabled
                    foreground: root.theme.text
                    accent: root.theme.accent
                    font.pixelSize: root.theme.summaryFontSize
                    placeholderText: "Application, PID, :port, /path, service, container, or device…"
                    onAccepted: if (!targetPalette.acceptCurrent()) root.searchAccepted(text)
                    onPressed: {
                        root.catalogRequested();
                        targetPalette.visible = true;
                    }
                    onTextEdited: {
                        root.catalogRequested();
                        targetPalette.visible = true;
                    }
                    Keys.onDownPressed: function(event) {
                        targetPalette.moveSelection(1);
                        event.accepted = true;
                    }
                    Keys.onUpPressed: function(event) {
                        targetPalette.moveSelection(-1);
                        event.accepted = true;
                    }
                }
                PlainText {
                    anchors.right: parent.right
                    anchors.rightMargin: 11
                    anchors.verticalCenter: parent.verticalCenter
                    text: "CTRL K"
                    color: root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                }
            }

            RowLayout {
                id: headerActions
                spacing: root.theme.gap

                IconButton {
                    iconName: "pick"
                    tooltipText: "Pick a window"
                    enabled: root.interactionEnabled && root.capabilities.windowPicker !== false
                    onClicked: root.pickRequested()
                }
                IconButton {
                    iconName: root.snapshot.samplingPaused ? "play" : "pause"
                    tooltipText: root.offline
                        ? "Offline report"
                        : (root.snapshot.samplingPaused ? "Resume live sampling" : "Pause live sampling")
                    enabled: root.interactionEnabled && !root.offline && !!(root.snapshot.target && root.snapshot.target.rootPid)
                    onClicked: root.pauseRequested()
                }
                IconButton {
                    iconName: "capsule"
                    tooltipText: "Saved reports"
                    enabled: root.interactionEnabled
                    onClicked: root.capsuleRequested()
                }
                IconButton {
                    iconName: "settings"
                    tooltipText: "X-Ray settings"
                    enabled: root.interactionEnabled
                    onClicked: root.settingsRequested()
                }
                IconButton {
                    iconName: "close"
                    tooltipText: "Close X-Ray"
                    onClicked: root.closeRequested()
                }
            }
        }

    TargetPalette {
            id: targetPalette
            visible: false
            z: 30
            x: searchContainer.x
            y: root.height + 5
            width: searchContainer.width
            height: implicitHeight
            theme: root.theme
            catalog: root.catalog
            query: searchField.text
            onSelected: function(query) {
                Qt.callLater(function() { root.searchAccepted(query); });
            }
    }
}
