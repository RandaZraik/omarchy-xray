import QtQuick
import "../controls"
import "../Format.js" as Format
import "../DetailDomains.js" as DetailDomains

Card {
    id: root
    objectName: "xrayCauseCard"

    property var snapshot: ({})
    readonly property var cause: (snapshot.context || {}).cause || {}
    readonly property var nodes: cause.nodes || []
    readonly property var displayNodes: nodes.slice(Math.max(0, nodes.length - 3))
    signal detailsRequested()
    title: "Launch chain"
    accentColor: theme.processAccent
    countText: String(cause.status || "UNAVAILABLE").toUpperCase()
    detailsCount: DetailDomains.count(DetailDomains.Cause, snapshot)
    interactive: nodes.length > 0
    onClicked: detailsRequested()

    body: Column {
        anchors.fill: parent
        anchors.topMargin: 7
        spacing: 0

        PlainText {
            width: parent.width
            height: root.theme.evidenceRowHeight
            text: root.cause.summary || "Launch details are unavailable"
            color: root.theme.text
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.bodyFontSize
            font.bold: true
            elide: Text.ElideRight
        }

        Repeater {
            model: root.displayNodes
            delegate: Item {
                required property var modelData
                required property int index
                width: parent.width
                height: root.theme.evidenceRowHeight

                Rectangle {
                    x: 10
                    y: index === 0 ? height / 2 : 0
                    width: 1
                    height: index === 0 ? parent.height / 2 : parent.height
                    color: root.accentColor
                    opacity: root.theme.connectorOpacity
                }
                Rectangle {
                    x: 6
                    anchors.verticalCenter: parent.verticalCenter
                    width: 9
                    height: 9
                    radius: 5
                    color: root.theme.surfaceMid
                    border.color: index === root.displayNodes.length - 1 ? root.accentColor : root.theme.border
                    border.width: root.theme.borderWidth
                }
                PlainText {
                    anchors.left: parent.left
                    anchors.leftMargin: 25
                    anchors.right: kindText.left
                    anchors.rightMargin: 7
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.title || "Process"
                    color: index === root.displayNodes.length - 1 ? root.theme.text : root.theme.muted
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.bodyFontSize
                    font.bold: index === root.displayNodes.length - 1
                    elide: Text.ElideRight
                }
                PlainText {
                    id: kindText
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: Format.icon(modelData.kind) + "  " + String(modelData.kind || "process").toUpperCase()
                    color: root.accentColor
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                }
            }
        }
    }
}
