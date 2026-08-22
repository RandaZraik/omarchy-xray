import QtQuick

Column {
    property var theme
    property string value: "—"
    property string label: ""
    property color accentColor: theme.metricText
    spacing: 2

    PlainText {
        text: parent.value
        color: parent.accentColor
        font.family: parent.theme.dataFont
        font.pixelSize: parent.theme.metricFontSize
        font.bold: true
    }

    PlainText {
        text: parent.label.toUpperCase()
        color: parent.theme.muted
        font.family: parent.theme.dataFont
        font.pixelSize: parent.theme.captionFontSize
        font.letterSpacing: parent.theme.labelTracking
    }
}
