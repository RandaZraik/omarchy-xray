import QtQuick
import qs.Ui
import "../controls"

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
        onClicked: root.cancelled()
    }

    Rectangle {
        z: 1
        width: Math.min(410, root.width - 40)
        height: 194
        anchors.centerIn: parent
        radius: root.theme.radius
        color: root.theme.panel
        border.color: root.theme.danger
        border.width: root.theme.borderWidth

        MouseArea { anchors.fill: parent; onClicked: {} }

        Column {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 12

            PlainText {
                width: parent.width
                text: root.action ? root.action.label + "?" : "Confirm action"
                color: root.theme.text
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.sectionFontSize
                font.bold: true
            }
            PlainText {
                width: parent.width
                text: root.action && root.action.confirmationTarget
                    ? "Target: " + root.action.confirmationTarget
                    : ""
                visible: text.length > 0
                color: root.theme.danger
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.bodyFontSize
                elide: Text.ElideMiddle
            }
            PlainText {
                width: parent.width
                text: "X-Ray will check the process again immediately before this action."
                color: root.theme.muted
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.bodyFontSize
                wrapMode: Text.WordWrap
            }
            Row {
                anchors.right: parent.right
                spacing: 8
                Button {
                    text: "Cancel"
                    bordered: true
                    focusable: true
                    onClicked: root.cancelled()
                }
                Button {
                    text: root.action ? root.action.label : "Continue"
                    bordered: true
                    selected: true
                    focusable: true
                    onClicked: if (root.action) root.confirmed(root.action.id)
                }
            }
        }
    }
}
