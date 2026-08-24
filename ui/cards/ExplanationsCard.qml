import QtQuick
import "../controls"
import "../DetailDomains.js" as DetailDomains

Card {
    id: root
    objectName: "xrayExplanationsCard"

    property var snapshot: ({})
    readonly property var rows: snapshot.explanations || []
    readonly property var timeline: snapshot.timeline || []
    signal detailsRequested()
    title: "Findings"
    accentColor: rows.some(function(row) { return row.tone === "attention"; })
        ? theme.alertAccent
        : theme.storageAccent
    countText: timeline.length + " CHANGES"
    detailsCount: DetailDomains.count(DetailDomains.Explanations, snapshot)
    interactive: rows.length > 0
    onClicked: detailsRequested()

    body: Column {
        anchors.fill: parent
        anchors.topMargin: 7
        spacing: 7

        Repeater {
            model: root.rows.slice(0, 3)
            delegate: Rectangle {
                required property var modelData
                width: parent.width
                height: Math.min(
                    76,
                    Math.max(48, (parent.height - 14) / Math.min(3, root.rows.length))
                )
                radius: root.theme.controlRadius
                color: modelData.tone === "attention"
                    ? root.theme.dangerSurface
                    : root.theme.tintedSurface(root.accentColor)

                Rectangle {
                    width: 2
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.topMargin: 8
                    anchors.bottomMargin: 8
                    anchors.left: parent.left
                    color: modelData.tone === "attention" ? root.theme.danger : root.accentColor
                }
                Column {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 11
                    anchors.rightMargin: 8
                    spacing: 3
                    Row {
                        width: parent.width
                        spacing: 6
                        PlainText {
                            width: Math.max(0, parent.width - statusText.width - 6)
                            text: modelData.title
                            color: modelData.tone === "attention" ? root.theme.danger : root.theme.text
                            font.family: root.theme.bodyFont
                            font.pixelSize: root.theme.bodyFontSize
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        PlainText {
                            id: statusText
                            text: String(modelData.status || "FOUND").toUpperCase()
                            color: root.accentColor
                            font.family: root.theme.dataFont
                            font.pixelSize: root.theme.microFontSize
                        }
                    }
                    PlainText {
                        width: parent.width
                        text: modelData.why || ""
                        color: root.theme.muted
                        font.family: root.theme.bodyFont
                        font.pixelSize: root.theme.captionFontSize
                        elide: Text.ElideRight
                    }
                }
            }
        }
    }
}
