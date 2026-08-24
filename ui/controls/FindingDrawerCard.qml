import QtQuick

Item {
    id: root

    required property var theme
    required property var row
    property color accentColor: theme.alertAccent

    readonly property int evidenceCount: (row.evidence || []).length
    readonly property bool attention: row.tone === "attention"
    implicitHeight: theme.drawerFindingBaseHeight
        + evidenceCount * theme.drawerFindingEvidenceHeight
        + (row.nextStep ? theme.drawerFindingNextHeight : 0) + theme.gap
    height: implicitHeight

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.theme.gap
        radius: root.theme.controlRadius
        color: root.attention ? root.theme.dangerSurface : root.theme.quietSurface

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.topMargin: root.theme.smallGap
            anchors.bottomMargin: root.theme.smallGap
            width: root.theme.telemetryRailWidth
            radius: root.theme.pillRadius
            color: root.attention ? root.theme.danger : root.accentColor
        }

        Column {
            anchors.fill: parent
            anchors.leftMargin: root.theme.pad + root.theme.smallGap
            anchors.rightMargin: root.theme.pad
            anchors.topMargin: root.theme.pad
            spacing: 4

            Row {
                width: parent.width

                PlainText {
                    width: Math.max(0, parent.width - findingStatus.width - root.theme.gap)
                    text: String(root.row.title || "Finding")
                    color: root.attention ? root.theme.danger : root.theme.text
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.labelFontSize
                    font.bold: true
                    elide: Text.ElideRight
                }
                PlainText {
                    id: findingStatus
                    text: String(root.row.meta || "FOUND")
                    color: root.attention ? root.theme.danger : root.accentColor
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
                model: root.row.evidence || []

                delegate: Row {
                    required property string modelData
                    required property int index
                    width: parent.width
                    height: 21
                    spacing: root.theme.smallGap

                    PlainText {
                        width: 16
                        text: String(index + 1).padStart(2, "0")
                        color: root.attention ? root.theme.danger : root.accentColor
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
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

            Rectangle {
                visible: !!root.row.nextStep
                width: parent.width
                height: 34
                radius: root.theme.controlRadius
                color: root.theme.controlActiveSurface

                PlainText {
                    anchors.left: parent.left
                    anchors.leftMargin: root.theme.pad
                    anchors.verticalCenter: parent.verticalCenter
                    text: "NEXT"
                    color: root.accentColor
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                    font.bold: true
                }
                PlainText {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: 48
                    anchors.rightMargin: root.theme.pad
                    anchors.verticalCenter: parent.verticalCenter
                    text: String(root.row.nextStep || "").replace(/\s+/g, " ")
                    color: root.theme.text
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.captionFontSize
                    elide: Text.ElideRight
                }
            }
        }
    }
}
