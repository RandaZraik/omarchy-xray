import QtQuick
import "../../ui/DetailDomains.js" as DetailDomains

QtObject {
    Component.onCompleted: {
        var separator = Qt.application.arguments.indexOf("--")
        if (separator < 0 || separator + 1 >= Qt.application.arguments.length)
            throw new Error("snapshot argument is required")
        var source = Qt.application.arguments.slice(separator + 1).join("")
        var snapshot = JSON.parse(source)
        var domains = [
            DetailDomains.Processes,
            DetailDomains.Connections,
            DetailDomains.Files,
            DetailDomains.Devices,
            DetailDomains.Runtime,
            DetailDomains.Cause,
            DetailDomains.Explanations,
            DetailDomains.Coverage,
            DetailDomains.Alternatives
        ]
        var counts = {}
        var rows = {}
        domains.forEach(function(domain) {
            counts[domain] = DetailDomains.count(domain, snapshot)
            rows[domain] = DetailDomains.rows(domain, snapshot)
        })
        console.log("XRAY_LIVE_DETAILS " + JSON.stringify({
            "counts": counts,
            "rows": rows
        }))
        Qt.quit()
    }
}
