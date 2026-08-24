import QtQuick

Item {
    id: root

    property var theme
    property string title: ""
    property string subtitle: ""
    property string meta: ""
    property string leadingText: ""
    property bool leadingBordered: true
    property color accentColor: theme.accent
    property bool emphasized: false
    property bool selected: false
    property bool interactive: true
    property color idleColor: theme.transparent
    property color selectedColor: theme.selected
    property color hoverColor: theme.selected
    property int titleElide: Text.ElideRight
    property int horizontalPadding: 8
    property int textSpacing: 1
    signal clicked()

    implicitHeight: theme.compactRowHeight
    height: implicitHeight

    Rectangle {
        anchors.fill: parent
        radius: root.theme.controlRadius
        color: root.selected
            ? root.selectedColor
            : root.interactive && hover.hovered ? root.hoverColor : root.idleColor
    }

    Rectangle {
        visible: root.selected
        width: root.theme.telemetryRailWidth
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: root.theme.smallGap
        anchors.bottomMargin: root.theme.smallGap
        radius: root.theme.pillRadius
        color: root.accentColor
    }

    Rectangle {
        id: leadingBadge
        visible: root.leadingText !== ""
        width: 24
        height: 24
        radius: root.theme.controlRadius
        anchors.left: parent.left
        anchors.leftMargin: root.horizontalPadding
        anchors.verticalCenter: parent.verticalCenter
        color: root.emphasized
            ? root.theme.tintedSurface(root.accentColor)
            : root.theme.transparent
        border.color: root.emphasized ? root.accentColor : root.theme.cardBorder
        border.width: root.leadingBordered ? root.theme.borderWidth : 0

        PlainText {
            anchors.centerIn: parent
            text: root.leadingText
            color: root.emphasized ? root.accentColor : root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.labelFontSize
            renderType: Text.NativeRendering
        }
    }

    Column {
        anchors.left: parent.left
        anchors.right: metaText.left
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: root.horizontalPadding
            + (leadingBadge.visible ? leadingBadge.width + root.theme.gap : 0)
            + (root.selected && !leadingBadge.visible ? root.theme.smallGap : 0)
        anchors.rightMargin: root.horizontalPadding
        spacing: root.textSpacing

        PlainText {
            width: parent.width
            text: root.title
            color: root.theme.text
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.labelFontSize
            font.bold: root.selected
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
        color: root.accentColor
        font.family: root.theme.dataFont
        font.pixelSize: root.theme.captionFontSize
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: root.horizontalPadding
        anchors.rightMargin: root.horizontalPadding
        height: root.theme.dividerWidth
        color: root.theme.cardBorder
        opacity: root.theme.subtleDividerOpacity
    }

    HoverHandler {
        id: hover
        enabled: root.interactive
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
    }
    TapHandler {
        enabled: root.interactive
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onTapped: root.clicked()
    }
}
