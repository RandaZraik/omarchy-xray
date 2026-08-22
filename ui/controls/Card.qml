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

    color: hover.hovered && interactive ? theme.raisedSurface : theme.quietSurface
    borderSpec: Commons.Border.flat(
        hover.hovered && interactive
            ? theme.hoveredBorder(accentColor)
            : theme.cardBorder,
        theme.borderWidth
    )
    radius: theme.radius
    clip: true

    Behavior on color { ColorAnimation { duration: root.theme.fastMotionDuration } }

    TextMetrics {
        id: detailsMetrics
        text: root.detailsLabel + " · " + root.detailsCount + "  →"
        font.family: root.theme.dataFont
        font.pixelSize: root.theme.captionFontSize
        font.bold: true
    }

    TextMetrics {
        id: headingMetrics
        text: root.title.toUpperCase() + (root.eyebrow ? "  ·  " + root.eyebrow.toUpperCase() : "")
        font.family: root.theme.bodyFont
        font.pixelSize: root.theme.bodyFontSize
        font.bold: true
        font.letterSpacing: root.theme.headingTracking
    }

    Column {
        anchors.fill: parent
        anchors.margins: root.theme.pad
        spacing: 0

        Row {
            id: header
            width: parent.width
            height: 30
            spacing: root.theme.smallGap

            PlainText {
                id: heading
                width: Math.max(0, parent.width - count.width - details.width - root.theme.smallGap * 2)
                anchors.verticalCenter: parent.verticalCenter
                text: root.title.toUpperCase() + (root.eyebrow ? "  ·  " + root.eyebrow.toUpperCase() : "")
                color: root.theme.headingColor(root.accentColor)
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.bodyFontSize
                font.bold: true
                font.letterSpacing: root.theme.headingTracking
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
                text: root.detailsLabel + " · " + root.detailsCount + "  →"
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

        Rectangle {
            width: parent.width
            height: root.theme.dividerWidth
            color: root.accentColor
            opacity: root.theme.dividerOpacity
        }

        Item {
            id: bodyItem
            width: parent.width
            height: parent.height - y
            clip: true
        }
    }

    HoverHandler { id: hover; enabled: root.interactive }
    TapHandler { enabled: root.interactive && root.bodyInteractive; onTapped: root.clicked() }
}
