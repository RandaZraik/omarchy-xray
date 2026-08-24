import QtQuick
import "../controls"
import "../Format.js" as Format
import "../DetailDomains.js" as DetailDomains

Card {
    id: root
    objectName: "xrayConnectionsCard"

    property var snapshot: ({})
    readonly property var rows: snapshot.connections || []
    signal detailsRequested()
    title: DetailDomains.title(DetailDomains.Connections)
    accentColor: theme.networkAccent
    countText: rows.length + " SOCKETS"
    detailsCount: DetailDomains.count(DetailDomains.Connections, snapshot)
    interactive: true
    onClicked: detailsRequested()

    body: Column {
        anchors.fill: parent
        spacing: 0

        EvidenceTableHeader {
            width: parent.width
            theme: root.theme
            columns: [
                {"text": "TYPE", "width": 0.12},
                {"text": "LOCAL", "width": 0.35},
                {"text": "REMOTE", "width": 0.38},
                {"text": "STATE", "width": 0.15}
            ]
        }

        Repeater {
            model: root.rows.slice(0, Math.max(0, Math.floor(
                (parent.height - root.theme.evidenceHeaderHeight)
                    / root.theme.evidenceRowHeight
            )))
            delegate: EvidenceTableRow {
                required property var modelData
                width: parent.width
                theme: root.theme
                cells: [
                    {"width": 0.12, "text": modelData.protocol || ""},
                    {"width": 0.35, "text": Format.addressPort(modelData.localAddress, modelData.localPort), "elide": Text.ElideMiddle},
                    {"width": 0.38, "text": Number(modelData.remotePort || 0) ? Format.addressPort(modelData.remoteAddress, modelData.remotePort) : "—", "elide": Text.ElideMiddle},
                    {"width": 0.15, "text": modelData.publicListener ? "ALL INTERFACES" : (modelData.listening ? "LISTEN" : String(modelData.state || "")), "color": modelData.publicListener ? root.theme.danger : root.accentColor, "fontSize": root.theme.microFontSize}
                ]
            }
        }
    }
}
