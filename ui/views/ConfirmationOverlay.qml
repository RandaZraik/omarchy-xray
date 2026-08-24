import QtQuick
import QtQuick.Layouts
import qs.Ui
import "../controls"
import "../Format.js" as Format

Rectangle {
    id: root

    required property var theme
    property var action: null
    signal cancelled()
    signal confirmed(string actionId)

    visible: root.action !== null
    focus: visible
    color: root.theme.confirmationScrim

    Keys.onEscapePressed: root.cancelled()

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.cancelled()
    }

    Rectangle {
        width: dialog.width + root.theme.gap * 2
        height: dialog.height + root.theme.gap * 2
        anchors.centerIn: dialog
        radius: root.theme.panelRadius + root.theme.gap
        color: root.theme.transparent
        border.color: root.theme.withAlpha(root.theme.danger, 0.2)
        border.width: root.theme.borderWidth
    }

    Rectangle {
        id: dialog
        z: 1
        width: Math.min(460, root.width - root.theme.drawerPadding * 2)
        height: 246
        anchors.centerIn: parent
        radius: root.theme.panelRadius
        border.color: root.theme.withAlpha(root.theme.danger, 0.56)
        border.width: root.theme.borderWidth
        gradient: Gradient {
            GradientStop { position: 0; color: root.theme.dangerSurface }
            GradientStop { position: 0.32; color: root.theme.surfaceHigh }
            GradientStop { position: 1; color: root.theme.surfaceMid }
        }

        MouseArea { anchors.fill: parent; onClicked: {} }

        AccentSignal {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: root.theme.borderWidth
            theme: root.theme
            accentColor: root.theme.danger
            fadePosition: 0.38
            radius: root.theme.panelRadius
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: root.theme.drawerPadding
            spacing: root.theme.gap

            RowLayout {
                Layout.fillWidth: true
                spacing: root.theme.gap

                Rectangle {
                    width: 38
                    height: 38
                    radius: root.theme.controlRadius
                    color: root.theme.dangerSurface
                    border.color: root.theme.withAlpha(root.theme.danger, 0.48)
                    border.width: root.theme.borderWidth

                    PlainText {
                        anchors.centerIn: parent
                        text: Format.icon(root.action ? root.action.icon : "stop")
                        color: root.theme.danger
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.sectionFontSize
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    PlainText {
                        Layout.fillWidth: true
                        text: "CONFIRM PROCESS CONTROL"
                        color: root.theme.danger
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
                        font.bold: true
                        font.letterSpacing: root.theme.utilityTracking
                    }
                    PlainText {
                        Layout.fillWidth: true
                        text: root.action ? root.action.label + "?" : "Confirm action"
                        color: root.theme.text
                        font.family: root.theme.bodyFont
                        font.pixelSize: root.theme.sectionFontSize
                        font.bold: true
                    }
                }
            }

            Rectangle {
                visible: targetText.text !== ""
                Layout.fillWidth: true
                implicitHeight: targetText.implicitHeight + root.theme.pad * 2
                radius: root.theme.controlRadius
                color: root.theme.surfaceLow
                border.color: root.theme.cardBorder
                border.width: root.theme.borderWidth

                PlainText {
                    id: targetText
                    anchors.fill: parent
                    anchors.margins: root.theme.pad
                    text: root.action && root.action.confirmationTarget
                        ? root.action.confirmationTarget : ""
                    color: root.theme.text
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.bodyFontSize
                    elide: Text.ElideMiddle
                }
            }

            PlainText {
                Layout.fillWidth: true
                text: "X-Ray checks the process identity again immediately before acting."
                color: root.theme.muted
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.bodyFontSize
                wrapMode: Text.WordWrap
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: root.theme.smallGap

                Item { Layout.fillWidth: true }
                ActionButton {
                    theme: root.theme
                    text: "Cancel"
                    foreground: root.theme.muted
                    onClicked: root.cancelled()
                }
                ActionButton {
                    theme: root.theme
                    variant: "danger"
                    text: root.action ? root.action.label : "Continue"
                    onClicked: if (root.action) root.confirmed(root.action.id)
                }
            }
        }
    }
}
