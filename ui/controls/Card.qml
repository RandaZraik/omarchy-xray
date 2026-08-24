import QtQuick
import qs.Commons as Commons
import qs.Ui

BorderSurface {
    id: root

    property var theme
    property string title: ""
    property string eyebrow: ""
    property string countText: ""
    property int detailsCount: 0
    property string detailsLabel: "VIEW ALL"
    property color accentColor: theme.accent
    property bool interactive: false
    property bool bodyInteractive: true
    property alias body: bodyItem.data
    signal clicked()

    color: hover.hovered && interactive
        ? theme.blend(theme.surfaceHigh, accentColor, 0.045)
        : theme.blend(theme.surfaceMid, accentColor, 0.018)
    borderSpec: Commons.Border.flat(
        hover.hovered && interactive
            ? theme.hoveredBorder(accentColor)
            : theme.cardBorder,
        theme.borderWidth
    )
    radius: theme.cardRadius
    clip: true

    Behavior on color { ColorAnimation { duration: root.theme.fastMotionDuration } }

    TextMetrics {
        id: detailsMetrics
        text: root.detailsLabel + "  " + root.detailsCount + "  ↗"
        font.family: root.theme.dataFont
        font.pixelSize: root.theme.captionFontSize
        font.bold: true
    }

    TextMetrics {
        id: headingMetrics
        text: root.title + (root.eyebrow ? "  ·  " + root.eyebrow.toUpperCase() : "")
        font.family: root.theme.bodyFont
        font.pixelSize: root.theme.labelFontSize
        font.bold: true
        font.letterSpacing: root.theme.headingTracking * 0.35
    }

    Column {
        anchors.fill: parent
        anchors.margins: root.theme.pad
        spacing: 0

        Row {
            id: header
            width: parent.width
            height: root.theme.cardHeaderHeight
            spacing: root.theme.smallGap

            PlainText {
                id: heading
                width: Math.max(0, parent.width - count.width - details.width - root.theme.smallGap * 2)
                anchors.verticalCenter: parent.verticalCenter
                text: root.title + (root.eyebrow ? "  ·  " + root.eyebrow.toUpperCase() : "")
                color: root.theme.headingColor(root.accentColor)
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.labelFontSize
                font.bold: true
                font.letterSpacing: root.theme.headingTracking * 0.35
                elide: Text.ElideRight
            }

            PlainText {
                id: count
                visible: root.countText !== ""
                    && headingMetrics.advanceWidth + implicitWidth + details.width
                        + root.theme.smallGap * 2 <= header.width
                width: visible ? Math.min(implicitWidth, parent.width * 0.32) : 0
                text: root.countText
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.captionFontSize
                anchors.verticalCenter: parent.verticalCenter
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideRight
            }

            PlainText {
                id: details
                visible: root.interactive && root.detailsCount > 0
                width: visible ? detailsMetrics.advanceWidth + root.theme.smallGap : 0
                text: root.detailsLabel + "  " + root.detailsCount + "  ↗"
                color: root.accentColor
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.captionFontSize
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
                horizontalAlignment: Text.AlignRight
            }

            TapHandler {
                enabled: root.interactive && !root.bodyInteractive
                onTapped: root.clicked()
            }
        }

        AccentSignal {
            width: parent.width
            theme: root.theme
            accentColor: root.accentColor
            fadePosition: 0.24
            opacity: root.theme.dividerOpacity
        }

        Item {
            id: bodyItem
            width: parent.width
            height: parent.height - y
            clip: true
        }
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: root.theme.borderWidth
        radius: Math.max(0, root.radius - root.theme.borderWidth)
        color: root.theme.transparent
        border.color: root.theme.surfaceHighlight
        border.width: root.theme.dividerWidth
        opacity: 0.45
    }

    HoverHandler { id: hover; enabled: root.interactive }
    TapHandler { enabled: root.interactive && root.bodyInteractive; onTapped: root.clicked() }
}
