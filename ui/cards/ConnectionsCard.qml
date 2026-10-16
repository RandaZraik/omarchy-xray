import QtQuick
import "../controls"
import "../Format.js" as Format
import "../DetailDomains.js" as DetailDomains
import "../domains/NetworkRows.js" as NetworkRows

Card {
    id: root
    objectName: "xrayConnectionsCard"

    property var snapshot: ({})
    readonly property var flows: ((snapshot.network || {}).flows || []).filter(function(row) { return row.active && !row.listening && Number(row.remotePort) })
    readonly property var listeners: (snapshot.connections || []).filter(function(row) { return row.listening })
    readonly property var rows: flows.length ? listeners.concat(flows) : snapshot.connections || []
    signal detailsRequested()
    title: DetailDomains.title(DetailDomains.Connections)
    accentColor: theme.networkAccent
    countText: flows.length ? flows.length + " CONNECTIONS" + (listeners.length ? " · " + listeners.length + " LISTEN" : "") : rows.length + " IP SOCKETS"
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
                {"text": "DESTINATION", "width": 0.46},
                {"text": "↑ UP", "width": 0.21},
                {"text": "↓ DOWN", "width": 0.21}
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
                    {"width": 0.46, "text": Number(modelData.remotePort || 0) ? (modelData.hostname || NetworkRows.endpoint(modelData)) : "Listen · " + Format.addressPort(modelData.localAddress, modelData.localPort), "elide": Text.ElideMiddle, "color": modelData.publicListener ? root.theme.danger : root.theme.text},
                    {"width": 0.21, "text": Format.rate(modelData.sentRate), "color": root.theme.networkAccent},
                    {"width": 0.21, "text": Format.rate(modelData.receivedRate), "color": root.theme.deviceAccent}
                ]
            }
        }
    }
}
