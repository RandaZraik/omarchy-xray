import QtQuick
import "../controls"
import "../Format.js" as Format
import "../DetailDomains.js" as DetailDomains

Card {
    id: root
    objectName: "xrayProcessCard"

    property var snapshot: ({})
    readonly property var rows: snapshot.processes || []
    readonly property int selectedPid: snapshot.target ? snapshot.target.ownerPid || 0 : 0
    signal processSelected(int pid)
    signal detailsRequested()
    title: "Launch & process tree"
    accentColor: theme.processAccent
    countText: rows.length + " processes"
    detailsCount: DetailDomains.count(DetailDomains.Processes, snapshot)
    interactive: true
    bodyInteractive: false
    onClicked: detailsRequested()

    body: Column {
        anchors.fill: parent
        anchors.topMargin: 5
        spacing: 0

        Repeater {
            model: root.rows.slice(0, Math.max(0, Math.floor(
                parent.height / root.theme.evidenceRowHeight
            )))
            delegate: Item {
                id: processRow
                required property var modelData
                required property int index
                width: parent.width
                height: root.theme.evidenceRowHeight

                readonly property int depth: Math.min(7, Number(modelData.depth || 0))
                readonly property int indent: depth * 14

                Rectangle {
                    anchors.fill: parent
                    radius: root.theme.controlRadius
                    color: Number(processRow.modelData.pid) === root.selectedPid
                        ? root.theme.accentSurface
                        : processHover.hovered
                            ? root.theme.surfaceHigh : root.theme.transparent
                }
                Rectangle {
                    visible: processRow.depth > 0
                    x: 8 + processRow.indent
                    y: 0
                    width: 1
                    height: parent.height / 2
                    color: root.theme.accent
                    opacity: root.theme.connectorOpacity
                }
                Rectangle {
                    visible: processRow.depth > 0
                    x: 8 + processRow.indent
                    y: parent.height / 2
                    width: 8
                    height: 1
                    color: root.theme.accent
                    opacity: root.theme.connectorOpacity
                }
                PlainText {
                    id: processName
                    anchors.left: parent.left
                    anchors.leftMargin: 9 + processRow.indent + (processRow.depth > 0 ? 12 : 0)
                    anchors.right: processMemory.left
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: String(processRow.modelData.name || "Process") + "  ·  PID " + processRow.modelData.pid
                    color: root.theme.text
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.bodyFontSize
                    font.bold: Number(processRow.modelData.pid) === root.selectedPid
                    elide: Text.ElideRight
                }
                PlainText {
                    id: processMemory
                    width: 70
                    anchors.right: processCpu.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: Format.bytes(processRow.modelData.memoryBytes)
                    color: root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.captionFontSize
                    horizontalAlignment: Text.AlignRight
                }
                PlainText {
                    id: processCpu
                    width: 52
                    anchors.right: parent.right
                    anchors.rightMargin: 7
                    anchors.verticalCenter: parent.verticalCenter
                    text: Format.percent(processRow.modelData.cpuPercent)
                    color: Number(processRow.modelData.cpuPercent || 0) >= 25 ? root.theme.danger : root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.captionFontSize
                    horizontalAlignment: Text.AlignRight
                }

                HoverHandler { id: processHover }
                TapHandler { onTapped: root.processSelected(Number(processRow.modelData.pid)) }
            }
        }
    }
}
