import QtQuick
import QtQuick.Controls as QQC

QQC.Button {
    id: root
    required property var theme
    property bool subtle: false
    implicitHeight: 36
    implicitWidth: Math.max(36, contentItem.implicitWidth + leftPadding + rightPadding)
    leftPadding: 12
    rightPadding: 12
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true
    contentItem: PlainText {
        text: root.text
        color: root.checked || root.hovered ? root.theme.text : root.theme.muted
        font.family: root.theme.readingFont
        font.pixelSize: root.theme.readingBodyFontSize
        font.weight: root.checked ? Font.DemiBold : Font.Normal
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 6
        color: root.down || root.checked ? root.theme.surfaceHigh
            : root.hovered ? root.theme.controlHoverSurface
            : root.subtle ? root.theme.transparent : root.theme.surfaceMid
        border.width: root.visualFocus ? root.theme.borderWidth : 0
        border.color: root.theme.accent
    }
}
