import QtQuick

Rectangle {
    required property var theme
    property color accentColor: theme.accent

    radius: theme.panelRadius
    border.color: theme.blend(theme.cardBorder, accentColor, 0.48)
    border.width: theme.borderWidth
    clip: true
    gradient: Gradient {
        GradientStop {
            position: 0
            color: theme.blend(theme.surfaceHigh, accentColor, 0.05)
        }
        GradientStop { position: 0.2; color: theme.surfaceMid }
        GradientStop { position: 1; color: theme.surfaceLow }
    }
}
