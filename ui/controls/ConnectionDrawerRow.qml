import QtQuick

Item {
    id: root

    required property var theme
    required property var row
    property color accentColor: theme.networkAccent

    implicitHeight: theme.drawerConnectionRowHeight
    height: implicitHeight

    Rectangle {
        anchors.fill: parent
        radius: root.theme.controlRadius
        color: root.theme.transparent
    }

    Rectangle {
        visible: root.row.exposed === true
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: root.theme.smallGap
        anchors.bottomMargin: root.theme.smallGap
        width: root.theme.telemetryRailWidth
        radius: root.theme.pillRadius
        color: root.row.publicListener === true
            ? root.theme.danger : root.accentColor
    }

    Rectangle {
        id: protocolBadge
        anchors.left: parent.left
        anchors.leftMargin: root.theme.pad
        anchors.verticalCenter: parent.verticalCenter
        width: 42
        height: 20
        radius: root.theme.controlRadius
        color: root.theme.tintedSurface(root.accentColor)

        PlainText {
            anchors.centerIn: parent
            text: String(root.row.protocol || "")
            color: root.accentColor
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            font.bold: true
        }
    }

    Column {
        anchors.left: protocolBadge.right
        anchors.right: statusText.left
        anchors.leftMargin: root.theme.gap
        anchors.rightMargin: root.theme.gap
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Row {
            width: parent.width
            spacing: root.theme.smallGap

            PlainText {
                width: root.row.remote ? Math.max(70, (parent.width - arrow.width - parent.spacing) * 0.44) : parent.width
                text: String(root.row.title || "")
                color: root.theme.text
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.labelFontSize
                elide: Text.ElideMiddle
            }

            PlainText {
                id: arrow
                visible: !!root.row.remote
                text: "→"
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.bodyFontSize
            }

            PlainText {
                visible: !!root.row.remote
                width: Math.max(0, parent.width - x)
                text: String(root.row.remote || "")
                color: root.theme.text
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.labelFontSize
                elide: Text.ElideMiddle
            }
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
        id: statusText
        anchors.right: parent.right
        anchors.rightMargin: root.theme.pad
        anchors.verticalCenter: parent.verticalCenter
        text: String(root.row.meta || "")
        color: root.row.publicListener === true ? root.theme.danger : root.accentColor
        font.family: root.theme.dataFont
        font.pixelSize: root.theme.microFontSize
        font.bold: root.row.exposed === true
    }
}
