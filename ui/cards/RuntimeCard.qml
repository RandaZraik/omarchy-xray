import QtQuick
import "../controls"
import "../DetailDomains.js" as DetailDomains
import "../domains/RuntimeRows.js" as RuntimeRows

Card {
    id: root
    objectName: "xrayRuntimeCard"

    property var snapshot: ({})
    readonly property var security: snapshot.security || {}
    readonly property var rows: RuntimeRows.cardRows(snapshot)
    signal detailsRequested()
    title: DetailDomains.title(DetailDomains.Runtime)
    accentColor: theme.runtimeAccent
    countText: security.seccomp && security.seccomp !== "Unknown" ? "SECCOMP " + String(security.seccomp).toUpperCase() : ""
    detailsCount: DetailDomains.count(DetailDomains.Runtime, snapshot)
    interactive: true
    onClicked: detailsRequested()

    body: Column {
        anchors.fill: parent
        anchors.topMargin: 3
        spacing: 0

        Repeater {
            model: root.rows.slice(0, Math.max(0, Math.floor(
                parent.height / root.theme.evidenceRowHeight
            )))
            delegate: EvidenceTableRow {
                required property var modelData
                width: parent.width
                height: root.theme.evidenceRowHeight
                theme: root.theme
                cells: [
                    {"width": 0.34, "text": modelData.title, "color": root.theme.muted, "fontFamily": root.theme.bodyFont},
                    {"width": 0.66, "text": modelData.subtitle, "elide": Text.ElideMiddle}
                ]
            }
        }
    }
}
