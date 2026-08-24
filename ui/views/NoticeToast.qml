import QtQuick
import "../controls"

Rectangle {
    id: root

    required property var theme
    property string message: ""

    visible: root.message !== ""
    width: Math.min(noticeText.implicitWidth + 52, parent ? parent.width - 32 : 460)
    height: 44
    radius: root.theme.pillRadius
    color: root.theme.surfaceHigh
    border.color: root.theme.accentBorder
    border.width: theme.borderWidth

    Rectangle {
        anchors.fill: parent
        anchors.margins: -root.theme.smallGap
        radius: root.theme.pillRadius
        color: root.theme.accentGlowSoft
        z: -1
    }

    Rectangle {
        width: 7
        height: 7
        radius: root.theme.pillRadius
        anchors.left: parent.left
        anchors.leftMargin: root.theme.pad
        anchors.verticalCenter: parent.verticalCenter
        color: root.theme.accent
    }

    PlainText {
        id: noticeText
        anchors.left: parent.left
        anchors.leftMargin: root.theme.pad * 2 + 7
        anchors.right: parent.right
        anchors.rightMargin: root.theme.pad
        anchors.verticalCenter: parent.verticalCenter
        text: root.message
        color: root.theme.text
        font.family: root.theme.bodyFont
        font.pixelSize: root.theme.bodyFontSize
        elide: Text.ElideMiddle
    }
}
