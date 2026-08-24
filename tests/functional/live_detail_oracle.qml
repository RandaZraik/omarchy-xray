import QtQuick
import "../../ui/DetailDomains.js" as DetailDomains
import "../../ui/DeviceSummary.js" as DeviceSummary
import "../../ui/ProcessEvidence.js" as ProcessEvidence
import "../../ui/domains/MetricRows.js" as MetricRows
import "../../ui/domains/RuntimeRows.js" as RuntimeRows

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
        var summaries = {}
        var details = {}
        var sections = {}
        var processSummary = ProcessEvidence.summary(snapshot.processes || [])
        domains.forEach(function(domain) {
            counts[domain] = DetailDomains.count(domain, snapshot)
            rows[domain] = DetailDomains.rows(domain, snapshot)
            summaries[domain] = DetailDomains.summary(
                domain, snapshot, rows[domain]
            )
            details[domain] = DetailDomains.unfilteredDetail(
                domain, snapshot, rows[domain], processSummary
            )
            sections[domain] = DetailDomains.preparePresentation(
                domain, rows[domain]
            ).sections.map(function(section) {
                var header = section.header || {}
                return {
                    "id": section.id,
                    "count": header.count,
                    "entryCount": header.entryCount,
                    "sourceCount": header.sourceCount,
                    "countLabel": header.countLabel
                }
            })
        })
        var devices = snapshot.devices || {}
        var selectedPid = Number((snapshot.target || {}).ownerPid || 0)
        var selectedRow = (snapshot.processes || []).find(function(row) {
            return Number(row.pid) === selectedPid
        }) || {}
        console.log("XRAY_LIVE_DETAILS " + JSON.stringify({
            "counts": counts,
            "rows": rows,
            "summaries": summaries,
            "details": details,
            "sections": sections,
            "cards": {
                "processSummary": processSummary,
                "selectedProcess": {
                    "pid": selectedPid,
                    "user": ProcessEvidence.user(selectedRow),
                    "state": ProcessEvidence.state(selectedRow),
                    "command": ProcessEvidence.command(selectedRow),
                    "presentation": ProcessEvidence.presentation(selectedRow)
                },
                "metrics": MetricRows.rows(snapshot),
                "devices": DeviceSummary.summarize(devices),
                "runtime": RuntimeRows.cardRows(snapshot)
            }
        }))
        Qt.quit()
    }
}
