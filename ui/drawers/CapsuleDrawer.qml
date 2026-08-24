import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.Ui
import "../controls"
import "../Format.js" as Format

DrawerSurface {
    id: root

    accentColor: theme.storageAccent

    property string status: ""
    property string capsulePath: ""
    property bool offline: false
    signal exportRequested()
    signal openRequested(string path)
    signal compareRequested(string path)
    signal reportRequested()
    signal closed()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.theme.drawerPadding
        spacing: root.theme.gap

        DrawerHeader {
            Layout.fillWidth: true
            theme: root.theme
            accentColor: root.accentColor
            eyebrow: "PRIVATE ARCHIVE"
            title: "Saved reports"
            detail: "Carry a redacted inspection forward without exposing live state."
            onClosed: root.closed()
        }

        Rectangle {
            Layout.fillWidth: true
            radius: root.theme.cardRadius
            color: root.theme.surfaceMid
            border.color: root.theme.cardBorder
            border.width: root.theme.borderWidth
            implicitHeight: exportColumn.implicitHeight + root.theme.pad * 2

            Column {
                id: exportColumn
                anchors.fill: parent
                anchors.margins: root.theme.pad
                spacing: root.theme.smallGap

                PlainText {
                    width: parent.width
                    text: "CAPTURE CURRENT SIGNAL"
                    color: root.theme.accent
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                    font.bold: true
                    font.letterSpacing: root.theme.utilityTracking
                }

                PlainText {
                    width: parent.width
                    text: "Save an offline snapshot or copy a readable redacted summary."
                    color: root.theme.muted
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.bodyFontSize
                    wrapMode: Text.WordWrap
                }

                ActionButton {
                    theme: root.theme
                    accentColor: root.accentColor
                    width: parent.width
                    text: "Export private report"
                    iconText: Format.icon("capsule")
                    leftAlign: true
                    enabled: !root.offline
                    opacity: enabled ? 1 : root.theme.disabledOpacity
                    onClicked: root.exportRequested()
                }

                ActionButton {
                    theme: root.theme
                    accentColor: root.accentColor
                    width: parent.width
                    text: "Copy redacted text report"
                    iconText: Format.icon("copy")
                    leftAlign: true
                    enabled: !root.offline
                    opacity: enabled ? 1 : root.theme.disabledOpacity
                    onClicked: root.reportRequested()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: root.theme.cardRadius
            color: root.theme.surfaceMid
            border.color: root.theme.cardBorder
            border.width: root.theme.borderWidth

            Column {
                anchors.fill: parent
                anchors.margins: root.theme.pad
                spacing: root.theme.smallGap

                PlainText {
                    width: parent.width
                    text: "OPEN OR COMPARE"
                    color: root.theme.accent
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                    font.bold: true
                    font.letterSpacing: root.theme.utilityTracking
                }

                PlainText {
                    width: parent.width
                    text: "Paste the path to an .xray.zip report."
                    color: root.theme.muted
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.bodyFontSize
                }

                ThemedTextField {
                    id: capsuleField
                    theme: root.theme
                    accentColor: root.accentColor
                    width: parent.width
                    placeholderText: "Path to an .xray.zip report"
                    text: root.capsulePath
                    onTextChanged: root.capsulePath = text
                }

                Row {
                    width: parent.width
                    spacing: root.theme.smallGap

                    ActionButton {
                        theme: root.theme
                        accentColor: root.accentColor
                        width: (parent.width - parent.spacing) / 2
                        text: "Open report"
                        onClicked: root.openRequested(root.capsulePath)
                    }
                    ActionButton {
                        theme: root.theme
                        accentColor: root.accentColor
                        variant: "primary"
                        width: (parent.width - parent.spacing) / 2
                        text: "Compare with current"
                        enabled: !root.offline
                        opacity: enabled ? 1 : root.theme.disabledOpacity
                        onClicked: root.compareRequested(root.capsulePath)
                    }
                }

                Rectangle {
                    visible: root.status !== ""
                    width: parent.width
                    height: statusText.implicitHeight + root.theme.pad * 2
                    radius: root.theme.controlRadius
                    color: root.theme.accentSurface
                    border.color: root.theme.accentBorder
                    border.width: root.theme.borderWidth

                    PlainText {
                        id: statusText
                        anchors.fill: parent
                        anchors.margins: root.theme.pad
                        text: root.status
                        color: root.theme.text
                        font.family: root.theme.bodyFont
                        font.pixelSize: root.theme.bodyFontSize
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }
}
