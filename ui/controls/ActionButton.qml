import QtQuick
import qs.Ui

Button {
    id: root

    required property var theme
    property string variant: "neutral"
    property color accentColor: theme.accent

    bordered: true
    focusable: true
    selected: variant !== "neutral"
    foreground: theme.text
    background: variant === "danger"
        ? theme.dangerSurface
        : variant === "primary"
            ? theme.blend(theme.surfaceHigh, accentColor, 0.12)
            : theme.surfaceLow
    accent: variant === "danger" ? theme.danger : accentColor
    fontFamily: theme.bodyFont
    radius: theme.controlRadius
}
