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
    Layout.preferredHeight: 54
    Layout.minimumHeight: 54
    Layout.maximumHeight: 54

    Rectangle {
        anchors.fill: parent
        radius: root.theme.cardRadius
        color: root.theme.surfaceLow
        border.color: root.theme.cardBorder
        border.width: root.theme.borderWidth

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: root.theme.telemetryRailWidth
            anchors.topMargin: root.theme.pad
            anchors.bottomMargin: root.theme.pad
            radius: root.theme.pillRadius
            color: root.theme.accent
        }
    }

    RowLayout {
        id: headerRow
        anchors.fill: parent
        anchors.leftMargin: root.theme.pad
        anchors.rightMargin: root.theme.smallGap
        spacing: root.theme.gap

        RowLayout {
            id: brandGroup
            Layout.preferredWidth: implicitWidth
            Layout.minimumWidth: implicitWidth
            spacing: root.theme.gap

            Rectangle {
                width: 31
                height: 31
                radius: root.theme.controlRadius
                color: root.theme.accentSurface
                border.color: root.theme.accentBorder
                border.width: root.theme.borderWidth

                PlainText {
                    anchors.centerIn: parent
                    text: Format.icon("xray")
                    color: root.theme.accent
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.sectionFontSize
                    renderType: Text.NativeRendering
                }
            }
            ColumnLayout {
                spacing: 0
                PlainText {
                    text: "X—RAY"
                    color: root.theme.text
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.sectionFontSize
                    font.bold: true
                    font.letterSpacing: root.theme.brandTracking * 0.45
                }
                PlainText {
                    text: "TRACE  /  CONTEXT  /  CONTROL"
                    color: root.theme.muted
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
                theme: root.theme
                iconName: "search"
                tooltipText: root.browserVisible ? "Hide target browser" : "Browse targets"
                onClicked: root.browserRequested()
            }
            IconButton {
                theme: root.theme
                iconName: "pick"
                tooltipText: "Pick a window"
                enabled: root.interactionEnabled && root.capabilities.windowPicker !== false
                onClicked: root.pickRequested()
            }
            IconButton {
                theme: root.theme
                iconName: root.snapshot.samplingPaused ? "play" : "pause"
                tooltipText: root.offline
                    ? "Offline report"
                    : (root.snapshot.samplingPaused ? "Resume live sampling" : "Pause live sampling")
                enabled: root.interactionEnabled && !root.offline
                    && !!(root.snapshot.target && root.snapshot.target.rootPid)
                onClicked: root.pauseRequested()
            }
            IconButton {
                theme: root.theme
                iconName: "capsule"
                tooltipText: "Saved reports"
                enabled: root.interactionEnabled
                onClicked: root.capsuleRequested()
            }
            IconButton {
                theme: root.theme
                iconName: "settings"
                tooltipText: "X-Ray settings"
                enabled: root.interactionEnabled
                onClicked: root.settingsRequested()
            }
            IconButton {
                theme: root.theme
                iconName: "close"
                tooltipText: "Close X-Ray"
                onClicked: root.closeRequested()
            }
        }
    }
}
