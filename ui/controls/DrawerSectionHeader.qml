import QtQuick
import "../Format.js" as Format

Item {
    id: root

    required property var theme
    property color accentColor: theme.accent
    property string iconName: "device"
    property string title: ""
    property int count: 0
    property string countLabel: ""
    property bool collapsed: false
    property bool interactive: true
    property bool pointerHovered: false
    signal toggled()

    implicitHeight: theme.drawerSectionRowHeight
    height: implicitHeight

    Rectangle {
        anchors.fill: parent
        anchors.topMargin: root.theme.smallGap
        anchors.bottomMargin: 2
        radius: root.theme.controlRadius
        color: root.pointerHovered
            ? root.theme.surfaceMid : root.theme.surfaceLow
    }

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: root.theme.smallGap
        anchors.bottomMargin: 2
        width: root.theme.telemetryRailWidth
        radius: root.theme.pillRadius
        color: root.accentColor
    }

    Row {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 1
        anchors.leftMargin: root.theme.pad
        anchors.rightMargin: root.theme.pad
        spacing: root.theme.smallGap

        PlainText {
            anchors.verticalCenter: parent.verticalCenter
            text: root.collapsed ? "▸" : "▾"
            color: root.accentColor
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
        }

        PlainText {
            anchors.verticalCenter: parent.verticalCenter
            text: Format.icon(root.iconName)
            color: root.accentColor
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
            renderType: Text.NativeRendering
        }

        PlainText {
            anchors.verticalCenter: parent.verticalCenter
            text: root.title
            color: root.theme.headingColor(root.accentColor)
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            font.bold: true
            font.letterSpacing: root.theme.utilityTracking
        }

        Item { width: Math.max(0, parent.width - x - countText.width) }

        PlainText {
            id: countText
            anchors.verticalCenter: parent.verticalCenter
            text: root.countLabel || String(root.count)
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
        }
    }

    HoverHandler {
        enabled: root.interactive
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onHoveredChanged: root.pointerHovered = hovered
    }
    TapHandler {
        enabled: root.interactive
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onTapped: root.toggled()
    }
}
