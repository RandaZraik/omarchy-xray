import QtQuick

PlainText {
    required property var theme
    color: theme.text
    font.family: theme.bodyFont
    font.pixelSize: theme.bodyFontSize
    wrapMode: Text.WordWrap
    lineHeight: 1.2
}
