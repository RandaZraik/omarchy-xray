import QtQuick
import qs.Ui
import "../Format.js" as Format

Button {
    required property var theme
    property string iconName: ""

    iconText: Format.icon(iconName)
    bordered: true
    focusable: true
    foreground: theme.text
    background: theme.surfaceLow
    accent: theme.accent
    fontFamily: theme.dataFont
    radius: theme.controlRadius
    horizontalPadding: theme.pad
    verticalPadding: theme.smallGap
}
