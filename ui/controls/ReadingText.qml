import QtQuick

PlainText {
    required property var theme
    color: theme.text
    font.family: theme.readingFont
    font.pixelSize: theme.readingBodyFontSize
    wrapMode: Text.WordWrap
    lineHeight: 1.2
}
