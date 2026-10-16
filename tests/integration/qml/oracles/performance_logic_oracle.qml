import QtQuick
import "../../../../ui/DetailDomains.js" as DetailDomains

QtObject {
    Component.onCompleted: {
        var separator = Qt.application.arguments.indexOf("--")
        var snapshot = JSON.parse(Qt.application.arguments[separator + 1])
        var domain = DetailDomains.Performance
        var rows = DetailDomains.rows(domain, snapshot)
        var anonymous = DetailDomains.rows(domain, {performance: {checks: [{}, {}]}})
        if (!anonymous[0].findingId || anonymous[0].findingId === anonymous[1].findingId) {
            console.log("XRAY_PERFORMANCE_ERROR anonymous measurements share an expansion key")
            Qt.exit(1)
            return
        }
        console.log("XRAY_PERFORMANCE_LOGIC " + JSON.stringify({
            count: DetailDomains.count(domain, snapshot),
            sections: DetailDomains.preparePresentation(domain, rows).sections.map(function(section) { return section.id }),
            first: rows[0],
            searchCount: DetailDomains.filterRows(rows, "throttled periods").length,
            touches: DetailDomains.patchTouches(domain, {performance: {}}),
            unrelated: DetailDomains.patchTouches(domain, {metrics: {}}),
            legacy: DetailDomains.rows(domain, {})
        }))
        Qt.quit()
    }
}
