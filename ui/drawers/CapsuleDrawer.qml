import QtQuick
import Quickshell
import qs.Ui
import "../controls"

Rectangle {
    id: root

    property var theme
    property string status: ""
    property string capsulePath: ""
    property bool offline: false
    signal exportRequested()
    signal openRequested(string path)
    signal compareRequested(string path)
    signal reportRequested()
    signal closed()

    color: theme.panel
    border.color: theme.border
    border.width: theme.borderWidth

    Column {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        Row {
            width: parent.width
            height: 35
            PlainText { width: parent.width - closeButton.width; text: "Saved reports"; color: root.theme.text; font.family: root.theme.bodyFont; font.pixelSize: root.theme.sectionFontSize; font.bold: true }
            IconButton { id: closeButton; iconName: "close"; onClicked: root.closed() }
        }

        PlainText { width: parent.width; text: "Save a private snapshot, open it later, or compare it with the process you are inspecting now."; color: root.theme.muted; font.family: root.theme.bodyFont; font.pixelSize: root.theme.bodyFontSize; wrapMode: Text.WordWrap }

        Rectangle { width: parent.width; height: root.theme.dividerWidth; color: root.theme.border; opacity: root.theme.subtleDividerOpacity }

        PlainText { text: "EXPORT"; color: root.theme.accent; font.family: root.theme.dataFont; font.pixelSize: root.theme.captionFontSize; font.letterSpacing: root.theme.labelTracking }
        Button { width: parent.width; text: "Export private report"; iconText: "󰆧"; bordered: true; focusable: true; leftAlign: true; enabled: !root.offline; opacity: enabled ? 1 : root.theme.disabledOpacity; onClicked: root.exportRequested() }
        Button { width: parent.width; text: "Copy redacted text report"; iconText: "󰆏"; bordered: true; focusable: true; leftAlign: true; enabled: !root.offline; opacity: enabled ? 1 : root.theme.disabledOpacity; onClicked: root.reportRequested() }

        PlainText { text: "OPEN OR COMPARE"; color: root.theme.accent; font.family: root.theme.dataFont; font.pixelSize: root.theme.captionFontSize; font.letterSpacing: root.theme.labelTracking }
        TextField {
            width: parent.width
            placeholderText: "Path to an .xray.zip report"
            text: root.capsulePath
            onTextChanged: root.capsulePath = text
        }
        Row {
            width: parent.width
            spacing: 8
            Button { width: (parent.width - parent.spacing) / 2; text: "Open report"; bordered: true; focusable: true; onClicked: root.openRequested(root.capsulePath) }
            Button { width: (parent.width - parent.spacing) / 2; text: "Compare with current"; bordered: true; focusable: true; enabled: !root.offline; opacity: enabled ? 1 : root.theme.disabledOpacity; onClicked: root.compareRequested(root.capsulePath) }
        }

        Rectangle {
            visible: root.status !== ""
            width: parent.width
            height: statusText.implicitHeight + 22
            radius: root.theme.radius
            color: root.theme.quietSurface
            border.color: root.theme.trace
            border.width: root.theme.borderWidth
            PlainText { id: statusText; anchors.fill: parent; anchors.margins: 11; text: root.status; color: root.theme.text; font.family: root.theme.bodyFont; font.pixelSize: root.theme.bodyFontSize; wrapMode: Text.WordWrap }
        }
    }
}
