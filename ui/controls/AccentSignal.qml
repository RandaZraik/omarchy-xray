import QtQuick

Rectangle {
    id: root

    required property var theme
    property color accentColor: theme.accent
    property real fadePosition: 0.3

    height: theme.telemetrySignalHeight
    gradient: Gradient {
        orientation: Gradient.Horizontal
        GradientStop { position: 0; color: root.accentColor }
        GradientStop {
            position: root.fadePosition
            color: root.theme.withAlpha(root.accentColor, 0.16)
        }
        GradientStop { position: 1; color: root.theme.transparent }
    }
}
