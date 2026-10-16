import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import "ui" as XRay
import "ui/views" as Views
import "ui/drawers" as Drawers
import "ui/controllers" as Controllers
import "ui/DetailDomains.js" as DetailDomains

ShellRoot {
    id: root
    property var fixture: JSON.parse(Quickshell.env("XRAY_PERFORMANCE_FIXTURE"))
    property int stage: 0
    property int attempts: 0
    property int initialCount: 0
    property string expandedId: ""

    XRay.XRayTheme { id: theme }
    Controllers.XRayController { id: controller }
    TestCase { id: driver; when: false }

    function require(value, message) {
        if (value) return
        console.log("XRAY_PERFORMANCE_ERROR " + message)
        Qt.exit(1)
        throw new Error(message)
    }

    function descendants(item) {
        var all = []
        var pending = [item]
        while (pending.length) {
            var next = pending.shift()
            all.push(next)
            if (next.children) pending = pending.concat(next.children.slice())
        }
        return all
    }

    Window {
        id: window
        width: Number(Quickshell.env("XRAY_PERFORMANCE_WIDTH")) || 1000
        height: 900
        visible: true
        color: theme.panel

        Views.AppHeader {
            id: header
            theme: theme
            width: parent.width
            height: 42
            snapshot: controller.snapshot
            offline: controller.offline
            onPerformanceRequested: controller.showDetails(DetailDomains.Performance)
        }
        Drawers.DetailDrawer {
            id: drawer
            theme: theme
            y: 50
            width: window.width < 1000 ? 520 : 620
            height: parent.height - y
            visible: controller.drawer === controller.detailsDrawer
            domain: controller.detailDomain
            snapshot: controller.detailSnapshot
        }
    }

    Timer {
        interval: 30
        running: true
        repeat: true
        onTriggered: {
            root.attempts++
            root.require(root.attempts < 150, "oracle timed out at stage " + root.stage)
            if (root.stage === 0) {
                controller.snapshot = root.fixture
                root.stage++
            } else if (root.stage === 1) {
                var button = root.descendants(header).find(function(item) {
                    return item.objectName === "xrayWhySlowButton"
                })
                root.require(button && button.enabled && button.width > 0, "Why slow button unavailable")
                var position = button.mapToItem(window.contentItem, 0, 0)
                root.require(position.x >= 0 && position.x + button.width <= window.width, "header button clipped")
                driver.mouseClick(button, button.width / 2, button.height / 2)
                root.stage++
            } else if (root.stage === 2) {
                root.require(drawer.visible && drawer.domain === DetailDomains.Performance, "button did not open performance drawer")
                root.initialCount = drawer.performanceCheckCount
                root.require(root.initialCount === root.fixture.performance.checks.length, "missing checks")
                root.require(drawer.rawRows.length === 0, "hidden technical rows were prepared")
                var overview = root.descendants(drawer).find(function(item) { return item.objectName === "xrayPerformanceOverview" })
                root.require(overview && overview.visible && !drawer.technicalDetails, "assessment is not the default view")
                root.require(overview.assessment.headline === "Clues worth investigating", "assessment lost observed clue")
                var headline = root.descendants(drawer).find(function(item) { return item.objectName === "xrayAssessmentHeadline" })
                root.require(headline.font.family === theme.bodyFont && headline.font.pixelSize === theme.sectionFontSize, "shared X-Ray typography missing")
                var toggle = root.descendants(drawer).find(function(item) { return item.objectName === "xrayPerformanceDetailsToggle" })
                root.require(toggle && toggle.visible, "measurements toggle missing")
                var capture = Quickshell.env("XRAY_PERFORMANCE_SCREENSHOT")
                if (capture) {
                    root.stage = 20
                    drawer.grabToImage(function(result) {
                        root.require(result.saveToFile(capture), "screenshot not saved")
                        driver.mouseClick(toggle, toggle.width / 2, toggle.height / 2)
                        root.stage = 21
                    })
                } else {
                    driver.mouseClick(toggle, toggle.width / 2, toggle.height / 2)
                    root.stage = 21
                }
            } else if (root.stage === 20) {
                return
            } else if (root.stage === 21) {
                root.require(drawer.technicalDetails, "measurements toggle did not open evidence")
                var check = root.descendants(drawer).find(function(item) {
                    return item.objectName === "xrayPerformanceCheck" && item.row.findingId.indexOf("performance-throttle-") === 0
                })
                root.require(check && !check.expanded, "measurement was not collapsed by default")
                root.expandedId = check.row.findingId
                var captureList = Quickshell.env("XRAY_PERFORMANCE_SCREENSHOT")
                if (captureList) {
                    root.stage = 20
                    drawer.grabToImage(function(result) {
                        root.require(result.saveToFile(captureList.replace(".png", "-measurements.png")), "measurements screenshot not saved")
                        driver.mouseClick(check, 30, 25)
                        root.stage = 22
                    })
                } else {
                    driver.mouseClick(check, 30, 25)
                    root.stage = 22
                }
            } else if (root.stage === 22) {
                root.require(Object.keys(drawer.expandedChecks).length === 1, "click did not expand one measurement")
                var evidence = root.descendants(drawer).filter(function(item) {
                    return item.visible && item.text !== undefined && String(item.text).indexOf("throttled periods") >= 0
                })
                root.require(evidence.length > 0, "measured throttling was not rendered")
                root.require(evidence.every(function(item) { return item.height >= item.implicitHeight - 1 }), "evidence was clipped")
                var captureExpanded = Quickshell.env("XRAY_PERFORMANCE_SCREENSHOT")
                if (captureExpanded) {
                    root.stage = 20
                    drawer.grabToImage(function(result) {
                        root.require(result.saveToFile(captureExpanded.replace(".png", "-expanded.png")), "expanded screenshot not saved")
                        drawer.applyFilterText("memory.events")
                        root.stage = 3
                    })
                } else {
                    drawer.applyFilterText("memory.events")
                    root.stage = 3
                }
            } else if (root.stage === 3) {
                root.require(drawer.rows.length > 0 && drawer.rows.length < root.initialCount, "search did not filter evidence")
                root.require(drawer.rows.every(function(row) { return row.title.indexOf("Memory-limit") >= 0 }), "search returned unrelated evidence")
                drawer.applyFilterText("")
                var sampling = root.descendants(controller).find(function(item) {
                    return typeof item.detailPatchRequested === "function"
                })
                root.require(sampling, "sampling controller unavailable")
                var updated = JSON.parse(JSON.stringify(root.fixture.performance))
                updated.checks[0].title = "Refreshed measured signal"
                updated.observed += 1
                updated.summary = "Refreshed performance summary"
                sampling.detailPatchRequested({performance: updated})
                drawer.toggleSection("cpu")
                root.stage++
            } else if (root.stage === 4) {
                root.require(drawer.allRows.some(function(row) { return row.title === "Refreshed measured signal" }), "open drawer missed refreshed evidence")
                root.require(root.descendants(drawer).some(function(item) {
                    return item.visible && item.text !== undefined
                        && String(item.text).indexOf("Refreshed performance summary") === 0
                }), "open drawer kept stale summary")
                root.require(drawer.expandedChecks[root.expandedId] === true, "refresh collapsed expanded measurement")
                root.require(drawer.displayRows.filter(function(row) { return row.section === "cpu" }).length === 1, "section did not collapse")
                drawer.toggleSection("cpu")
                controller.offline = true
                controller.snapshot = {target: {rootPid: 7}, performance: root.fixture.performance}
                controller.showDetails(DetailDomains.Performance)
                root.stage++
            } else if (root.stage === 5) {
                root.require(drawer.allRows.length === root.initialCount, "offline checks changed")
                controller.snapshot = {target: {rootPid: 7}}
                controller.showDetails(DetailDomains.Performance)
                root.stage++
            } else {
                root.require(drawer.allRows.length === 1, "old capsule has no fallback")
                root.require(drawer.allRows[0].meta === "UNAVAILABLE", "old capsule claims measured data")
                console.log("XRAY_PERFORMANCE " + JSON.stringify({checks: root.initialCount, overview: true, clicked: true, filtered: true, refreshed: true, collapsed: true, offline: true, legacy: true}))
                Qt.quit()
            }
        }
    }
}
