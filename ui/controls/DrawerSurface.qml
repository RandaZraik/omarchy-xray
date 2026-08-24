import QtQuick

Rectangle {
    required property var theme
    property color accentColor: theme.accent

    radius: theme.consoleRadius
    border.color: theme.consoleBorder
    border.width: theme.borderWidth
    clip: true
    color: theme.consoleSurface
}
