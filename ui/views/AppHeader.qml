import QtQuick
import QtQuick.Layouts
import qs.Commons
import "../controls"
import "../Format.js" as Format

Item {
    id: root

    required property var theme
    property var capabilities: ({})
    property var snapshot: ({})
    property bool offline: false
    property bool interactionEnabled: true
    property bool browserVisible: true

    signal browserRequested()
    signal pickRequested()
    signal pauseRequested()
    signal capsuleRequested()
    signal settingsRequested()
    signal closeRequested()

    Layout.fillWidth: true
    Layout.preferredHeight: 46
    Layout.minimumHeight: 46
    Layout.maximumHeight: 46

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

        Item { Layout.fillWidth: true }

        RowLayout {
            id: headerActions
            spacing: root.theme.gap

            IconButton {
                iconName: "search"
                tooltipText: root.browserVisible ? "Hide target browser" : "Browse targets"
                onClicked: root.browserRequested()
            }
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
                enabled: root.interactionEnabled && !root.offline
                    && !!(root.snapshot.target && root.snapshot.target.rootPid)
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
}
