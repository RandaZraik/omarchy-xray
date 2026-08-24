import QtQuick

Item {
    id: root

    required property var theme
    required property var row
    property color accentColor: theme.alertAccent

    readonly property var evidenceRows: row.evidence || []
    readonly property int evidenceCount: Number(row.evidenceCount || 0)
    readonly property int hiddenEvidenceCount: Math.max(
        0, evidenceCount - evidenceRows.length
    )
    readonly property bool attention: row.tone === "attention"
    readonly property color signalColor: attention ? theme.danger : accentColor
    readonly property int evidenceHeight: evidenceRows.length
        * theme.drawerFindingEvidenceHeight
        + (hiddenEvidenceCount > 0 ? theme.drawerFindingEvidenceHeight : 0)
    implicitHeight: theme.drawerFindingBaseHeight + evidenceHeight
        + (row.nextStep ? theme.drawerFindingNextHeight : 0) + theme.smallGap
    height: implicitHeight

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: root.theme.smallGap
        anchors.bottomMargin: root.theme.smallGap
        width: root.theme.telemetryRailWidth
        radius: root.theme.pillRadius
        color: root.signalColor
    }

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: root.theme.pad + root.theme.smallGap
        anchors.rightMargin: root.theme.pad
        anchors.topMargin: root.theme.pad
        spacing: 3

        Row {
            width: parent.width
            spacing: root.theme.gap

            PlainText {
                width: Math.max(0, parent.width - findingMeta.width - parent.spacing)
                text: String(root.row.title || "Finding")
                color: root.theme.text
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.labelFontSize
                font.bold: true
                elide: Text.ElideRight
            }
            PlainText {
                id: findingMeta
                text: String(root.row.meta || "OBSERVED")
                    + (root.evidenceCount ? "  ·  " + root.evidenceCount : "")
                color: root.signalColor
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.microFontSize
                font.bold: true
            }
        }

        PlainText {
            width: parent.width
            text: String(root.row.subtitle || "").replace(/\s+/g, " ")
            color: root.theme.muted
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.captionFontSize
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        Repeater {
            model: root.evidenceRows

            delegate: Row {
                required property string modelData
                required property int index
                width: parent.width
                height: root.theme.drawerFindingEvidenceHeight
                spacing: root.theme.smallGap

                PlainText {
                    width: 18
                    height: parent.height
                    text: String(index + 1).padStart(2, "0")
                    color: root.signalColor
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                    verticalAlignment: Text.AlignVCenter
                }
                PlainText {
                    width: Math.max(0, parent.width - x)
                    height: parent.height
                    text: String(modelData).replace(/\s+/g, " ")
                    color: root.theme.text
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.captionFontSize
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideMiddle
                }
            }
        }

        PlainText {
            visible: root.hiddenEvidenceCount > 0
            width: parent.width
            height: visible ? root.theme.drawerFindingEvidenceHeight : 0
            text: "+ " + root.hiddenEvidenceCount
                + " more records in " + String(root.row.domain || "evidence")
            color: root.signalColor
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            font.bold: true
            verticalAlignment: Text.AlignVCenter
        }

        Item {
            visible: !!root.row.nextStep
            width: parent.width
            height: visible ? root.theme.drawerFindingNextHeight : 0

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: root.theme.dividerWidth
                color: root.theme.cardBorder
                opacity: root.theme.subtleDividerOpacity
            }

            PlainText {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: "→  " + String(root.row.nextStep || "").replace(/\s+/g, " ")
                color: root.theme.text
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.captionFontSize
                elide: Text.ElideRight
            }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: root.theme.dividerWidth
        color: root.theme.cardBorder
        opacity: root.theme.subtleDividerOpacity
    }
}
