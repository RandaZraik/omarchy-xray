import QtQuick

Item {
    id: root

    required property var theme
    property string title: ""
    property string subtitle: ""
    property string detail: ""
    property string meta: ""
    property string iconText: ""
    property color accentColor: theme.accent
    property color contentColor: accentColor
    property bool iconHighlighted: false
    property bool showRail: false
    property bool emphasized: false
    property int titleElide: Text.ElideRight
    property int rowHeight: theme.drawerConnectionRowHeight

    implicitHeight: rowHeight
    height: implicitHeight

    Rectangle {
        visible: root.showRail
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: root.theme.smallGap
        anchors.bottomMargin: root.theme.smallGap
        width: root.theme.telemetryRailWidth
        radius: root.theme.pillRadius
        color: root.contentColor
    }

    Rectangle {
        id: iconTile
        anchors.left: parent.left
        anchors.leftMargin: root.theme.pad
        anchors.verticalCenter: parent.verticalCenter
        width: 26
        height: 26
        radius: root.theme.controlRadius
        color: root.iconHighlighted
            ? root.theme.tintedSurface(root.contentColor) : root.theme.transparent

        PlainText {
            anchors.centerIn: parent
            text: root.iconText
            color: root.contentColor
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.labelFontSize
            renderType: Text.NativeRendering
        }
    }

    Column {
        anchors.left: iconTile.right
        anchors.right: metaText.left
        anchors.leftMargin: root.theme.smallGap
        anchors.rightMargin: root.theme.gap
        anchors.verticalCenter: parent.verticalCenter
        spacing: 1

        PlainText {
            width: parent.width
            text: root.title
            color: root.emphasized ? root.contentColor : root.theme.text
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.labelFontSize
            font.bold: root.emphasized
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
        PlainText {
            visible: root.detail !== ""
            width: parent.width
            text: root.detail
            color: root.theme.muted
            opacity: 0.78
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            elide: Text.ElideMiddle
        }
    }

    PlainText {
        id: metaText
        anchors.right: parent.right
        anchors.rightMargin: root.theme.pad
        anchors.verticalCenter: parent.verticalCenter
        text: root.meta
        color: root.contentColor
        font.family: root.theme.dataFont
        font.pixelSize: root.theme.microFontSize
        font.bold: root.emphasized
    }
}
