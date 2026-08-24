import QtQuick

Item {
    id: root

    required property var theme
    required property var row
    property color accentColor: theme.processAccent
    property bool first: false
    property bool last: false

    implicitHeight: theme.drawerCauseRowHeight
    height: implicitHeight

    Rectangle {
        x: root.theme.drawerCauseConnectorX
        y: root.first ? parent.height / 2 : 0
        width: root.theme.dividerWidth
        height: root.last ? parent.height / 2 : parent.height
        color: root.accentColor
        opacity: root.theme.connectorOpacity
    }

    Rectangle {
        anchors.left: parent.left
        anchors.leftMargin: root.theme.pad
        anchors.verticalCenter: parent.verticalCenter
        width: root.theme.drawerCauseBadgeSize
        height: width
        radius: root.theme.pillRadius
        color: root.theme.tintedSurface(root.accentColor)
        border.color: root.accentColor
        border.width: root.theme.borderWidth

        PlainText {
            anchors.centerIn: parent
            text: String(root.row.step || "")
            color: root.accentColor
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
            font.bold: true
        }
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: root.theme.drawerCauseTextIndent
        anchors.right: kindText.left
        anchors.rightMargin: root.theme.gap
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        PlainText {
            width: parent.width
            text: String(root.row.title || "Process")
            color: root.theme.text
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.labelFontSize
            font.bold: true
            elide: Text.ElideRight
        }
        PlainText {
            width: parent.width
            text: String(root.row.subtitle || "")
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
            elide: Text.ElideMiddle
        }
    }

    PlainText {
        id: kindText
        anchors.right: parent.right
        anchors.rightMargin: root.theme.pad
        anchors.verticalCenter: parent.verticalCenter
        text: String(root.row.meta || "")
        color: root.accentColor
        font.family: root.theme.dataFont
        font.pixelSize: root.theme.microFontSize
    }
}
