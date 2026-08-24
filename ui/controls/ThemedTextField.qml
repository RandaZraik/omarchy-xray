import QtQuick
import qs.Ui

TextField {
    id: root

    required property var theme
    property color accentColor: theme.accent
    property color idleSurface: theme.surfaceHigh
    property color focusSurface: theme.focusedSurface(accentColor)
    property color idleBorder: theme.cardBorder
    property color focusBorder: theme.focusedBorder(accentColor)

    foreground: theme.text
    accent: accentColor
    selectionTint: theme.selected
    placeholderTextColor: theme.muted
    font.family: theme.dataFont
    background: Rectangle {
        radius: root.theme.controlRadius
        color: root.activeFocus ? root.focusSurface : root.idleSurface
        border.color: root.activeFocus ? root.focusBorder : root.idleBorder
        border.width: root.theme.borderWidth
    }
}
