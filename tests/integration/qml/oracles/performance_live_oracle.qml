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
    property int targetPid: Number(Quickshell.env("XRAY_LIVE_PID"))
    property int stage: 0
    property double deadline: Date.now() + 12000
    property string firstSample: ""

    XRay.XRayTheme { id: theme }
    Controllers.XRayController { id: controller }
    TestCase { id: driver; when: false }

    function require(value, message) {
        if (value) return
        poll.stop()
        console.log("XRAY_LIVE_PERFORMANCE_ERROR " + message)
        controller.close()
        Qt.exit(1)
        throw new Error(message)
    }

    function findObject(item, name) {
        if (item.objectName === name) return item
        for (var index = 0; index < (item.children || []).length; index++) {
            var found = findObject(item.children[index], name)
            if (found) return found
        }
        return null
    }

    Window {
        width: 1000
        height: 720
        visible: true
        color: theme.panel
        Views.IdentityBar {
            id: identity
            theme: theme
            width: parent.width
            snapshot: controller.snapshot
            enabled: !controller.interactionBlocked
            onPerformanceRequested: controller.showDetails(DetailDomains.Performance)
        }
        Drawers.DetailDrawer {
            id: drawer
            theme: theme
            y: identity.height + theme.gap
            width: 740
            height: parent.height - y
            visible: controller.drawer === controller.detailsDrawer
            domain: controller.detailDomain
            snapshot: controller.detailSnapshot
        }
    }

    Timer {
        id: poll
        interval: 30
        running: true
        repeat: true
        property bool advancing: false
        onTriggered: {
            // QtTest input can process another timer tick before a step finishes.
            if (advancing) return
            advancing = true
            try { advance() } finally { advancing = false }
        }
        function advance() {
            root.require(Date.now() < root.deadline, "timeout at stage " + root.stage + ": " + controller.notice)
            if (root.stage === 0) {
                controller.open(JSON.stringify({query: "pid:" + root.targetPid}))
                root.stage++
            } else if (root.stage === 1) {
                if (controller.busy || !(controller.snapshot.target || {}).rootPid) return
                root.require(controller.snapshot.target.rootPid === root.targetPid, "wrong live process")
                root.require(controller.snapshot.performance.checks.length > 0, "backend omitted performance")
                root.firstSample = controller.snapshot.generatedAt
                var button = root.findObject(identity, "xrayPerformanceButton")
                root.require(button && button.enabled, "live performance button unavailable")
                driver.mouseClick(button, button.width / 2, button.height / 2)
                root.stage++
            } else if (root.stage === 2) {
                root.require(drawer.visible && drawer.domain === DetailDomains.Performance, "live button did not open drawer")
                controller.refresh()
                root.stage++
            } else {
                if (controller.refreshInFlight || controller.detailSnapshot.generatedAt === root.firstSample) return
                var work = controller.detailSnapshot.performance.checks.find(function(check) {
                    return check.id === "performance-cpu-work"
                })
                root.require(work && work.status === "Quiet", "live CPU interval unavailable")
                root.require(work.measurements.processes === 1, "wrong sampled process count")
                root.require(drawer.performanceCheckCount === controller.snapshot.performance.checks.length, "drawer lost backend checks")
                var overview = root.findObject(drawer, "xrayPerformanceOverview")
                root.require(overview && overview.visible && overview.assessment.context.indexOf("1 process sampled") >= 0, "live assessment did not receive measured interval")
                console.log("XRAY_LIVE_PERFORMANCE " + JSON.stringify({pid: root.targetPid, checks: drawer.performanceCheckCount, refreshed: true, status: work.status}))
                poll.stop()
                controller.close()
                Qt.quit()
            }
        }
    }
}
