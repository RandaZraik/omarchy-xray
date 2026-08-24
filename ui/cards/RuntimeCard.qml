import QtQuick
import "../controls"
import "../DetailDomains.js" as DetailDomains

Card {
    id: root
    objectName: "xrayRuntimeCard"

    property var snapshot: ({})
    readonly property var context: snapshot.context || {}
    readonly property var security: snapshot.security || {}
    readonly property var service: context.service || {}
    readonly property var container: context.container || {}
    readonly property var rows: [
        {"title": "Service", "subtitle": service.id || "No managing service found"},
        {"title": "Container", "subtitle": container.name || "No container found"},
        {"title": "Identity", "subtitle": security.statusAvailable === true ? "UID " + security.uid + " · GID " + security.gid : "Unavailable"},
        {"title": "Isolation", "subtitle": Object.keys(security.namespaces || {}).length + " namespaces · seccomp " + (security.seccomp || "unknown")},
        {"title": "Capabilities", "subtitle": security.capabilitiesKnown === true ? ((security.capabilities || []).join(", ") || "No effective capabilities") : "Unknown"},
        {"title": "Control group", "subtitle": context.launch && context.launch.unit ? context.launch.unit : "No user unit identified"}
    ]
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
