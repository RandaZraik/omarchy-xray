import QtQuick
import "../controls"

Rectangle {
    id: root

    required property var theme
    property string message: ""

    visible: root.message !== ""
    width: Math.min(noticeText.implicitWidth + 28, parent ? parent.width - 32 : 420)
    height: 38
    radius: root.theme.radius
    color: root.theme.panel
    border.color: root.theme.trace
    border.width: theme.borderWidth

    PlainText {
        id: noticeText
        anchors.centerIn: parent
        width: Math.min(implicitWidth, root.width - 20)
        text: root.message
        color: root.theme.text
        font.family: root.theme.bodyFont
        font.pixelSize: root.theme.bodyFontSize
        elide: Text.ElideMiddle
    }
}
