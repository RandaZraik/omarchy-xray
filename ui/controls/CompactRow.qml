import QtQuick

Item {
    id: root

    property var theme
    property string title: ""
    property string subtitle: ""
    property string meta: ""
    property bool selected: false
    property bool interactive: true
    property color idleColor: theme.transparent
    property int titleElide: Text.ElideRight
    property int horizontalPadding: 8
    property int textSpacing: 1
    signal clicked()

    height: 38

    Rectangle {
        anchors.fill: parent
        radius: root.theme.radius
        color: root.selected || (root.interactive && hover.hovered)
            ? root.theme.selected
            : root.idleColor
    }

    Column {
        anchors.left: parent.left
        anchors.right: metaText.left
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: root.horizontalPadding
        anchors.rightMargin: root.horizontalPadding
        spacing: root.textSpacing

        PlainText {
            width: parent.width
            text: root.title
            color: root.theme.text
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.labelFontSize
            elide: root.titleElide
        }

        PlainText {
            width: parent.width
            text: root.subtitle
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
            elide: Text.ElideMiddle
        }
    }

    PlainText {
        id: metaText
        anchors.right: parent.right
        anchors.rightMargin: root.horizontalPadding
        anchors.verticalCenter: parent.verticalCenter
        text: root.meta
        color: root.theme.accent
        font.family: root.theme.dataFont
        font.pixelSize: root.theme.captionFontSize
    }

    HoverHandler { id: hover }
    TapHandler { enabled: root.interactive; onTapped: root.clicked() }
}
