import QtQuick
import QtQuick.Layouts
import "../controls"
import "../Format.js" as Format

Rectangle {
    id: root

    required property var theme
    property var capabilities: ({})
    property var snapshot: ({})
    property bool browserOpen: true
    property bool offline: false
    property bool interactionEnabled: true
    readonly property var target: snapshot.target || ({})

    signal browserRequested()
    signal pickRequested()
    signal pauseRequested()
    signal capsuleRequested()
    signal settingsRequested()
    signal closeRequested()

    Layout.fillWidth: true
    Layout.preferredHeight: 42
    Layout.minimumHeight: 42
    Layout.maximumHeight: 42

    color: theme.transparent

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: root.theme.pad
        anchors.rightMargin: root.theme.smallGap
        spacing: root.theme.gap

        RowLayout {
            Layout.preferredWidth: 230
            spacing: root.theme.smallGap

            Item {
                objectName: "xrayBrandMark"
                width: 27
                height: 31

                PlainText {
                    anchors.centerIn: parent
                    text: Format.icon("xray")
                    color: root.theme.accent
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.heroFontSize
                    renderType: Text.NativeRendering
                }
            }
            ColumnLayout {
                spacing: 0

                PlainText {
                    text: "X-RAY"
                    color: root.theme.text
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.brandFontSize
                    font.bold: true
                    font.letterSpacing: root.theme.brandTracking
                }
                PlainText {
                    text: "TRACE  /  CONTEXT  /  CONTROL"
                    color: root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.brandTaglineFontSize
                    font.letterSpacing: root.theme.taglineTracking
                }
            }
        }

        Item { Layout.fillWidth: true }

        RowLayout {
            spacing: 3

            IconButton {
                theme: root.theme
                iconName: "search"
                selected: root.browserOpen
                tooltipText: root.browserOpen
                    ? "Hide target catalog" : "Search targets (Ctrl+K)"
                enabled: root.interactionEnabled
                onClicked: root.browserRequested()
            }
            IconButton {
                theme: root.theme
                iconName: "pick"
                tooltipText: "Pick a window"
                enabled: root.interactionEnabled
                    && root.capabilities.windowPicker !== false
                onClicked: root.pickRequested()
            }
            IconButton {
                theme: root.theme
                iconName: root.snapshot.samplingPaused ? "play" : "pause"
                tooltipText: root.snapshot.samplingPaused
                    ? "Resume live sampling" : "Pause live sampling"
                enabled: root.interactionEnabled && !root.offline
                    && !!(root.target && root.target.rootPid)
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
