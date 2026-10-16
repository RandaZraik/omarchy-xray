import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import "ui" as XRay
import "ui/drawers" as Drawers
import "ui/controllers" as Controllers
import "ui/DetailDomains.js" as DetailDomains

ShellRoot {
    id: root
    property int targetPid: Number(Quickshell.env("XRAY_LIVE_PID"))
    property int port: Number(Quickshell.env("XRAY_LIVE_PORT"))
    property bool captureRequired: Quickshell.env("XRAY_CAPTURE_REQUIRED") === "1"
    property string expectedName: Quickshell.env("XRAY_EXPECTED_NAME")
    property int stage: 0
    property string copied: ""
    property bool selectedForCopy: false
    property int originalInspection: 0
    property var observed: ({})
    property double deadline: Date.now() + 25000
    XRay.XRayTheme { id: theme }
    Controllers.XRayController { id: controller }
    TestCase { id: driver; when: false }
    function require(value, message) {
        if (value) return
        poll.stop()
        console.log("XRAY_NETWORK_LIVE_ERROR " + message)
        controller.close()
        Qt.exit(1)
        throw new Error(message)
    }
    function find(item, name) {
        if (item.objectName === name) return item
        for (var i = 0; i < (item.children || []).length; i++) {
            var result = find(item.children[i], name)
            if (result) return result
        }
        return null
    }
    function click(name) {
        var button = find(drawer, name)
        require(button && button.visible && button.enabled, "button unavailable: " + name)
        driver.mouseClick(button, button.width / 2, button.height / 2)
    }
    function flow() {
        return ((controller.detailSnapshot.network || {}).flows || []).find(function(row) { return row.remotePort === root.port })
    }
    Window {
        width: 820
        height: 720
        visible: true
        color: theme.panel
        Drawers.DetailDrawer {
            id: drawer
            anchors.fill: parent
            theme: theme
            visible: controller.drawer === controller.detailsDrawer
            domain: controller.detailDomain
            snapshot: controller.detailSnapshot
            networkBusy: controller.networkBusy
            onNetworkConfigured: function(options) { controller.configureNetwork(options) }
            onNetworkOwnerSelected: function(owner) { controller.selectProcessAfterPointer(Number(owner.pid), owner) }
            onCopyRequested: function(text) { root.copied = text }
        }
    }
    Timer {
        id: poll
        interval: 100
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
            root.require(Date.now() < root.deadline, "timeout stage " + root.stage + ": " + controller.notice)
            if (root.stage === 0) {
                controller.open(JSON.stringify({query: "pid:" + root.targetPid}))
                root.stage++
                return
            }
            if (controller.busy || controller.refreshInFlight || controller.networkBusy) return
            var view = root.find(drawer, "xrayNetworkView")
            var network = controller.detailSnapshot.network || {}
            var flow = root.flow()
            if (root.stage === 1) {
                if (!(controller.snapshot.target || {}).rootPid) return
                root.require(controller.snapshot.target.rootPid === root.targetPid, "wrong target")
                root.originalInspection = controller.inspectionGeneration
                controller.showDetails(DetailDomains.Connections)
                root.stage++
            } else if (root.stage === 2) {
                if (!flow || !(flow.sentBytes > 0) || !(flow.receivedBytes > 0)) { controller.refresh(); return }
                root.require(flow.owners[0].pid === root.targetPid, "wrong flow owner")
                root.require(view && view.visible && view.mapRows.some(function(row) { return row.id === flow.id }), "live flow missing in map")
                if (!root.selectedForCopy) {
                    view.choose(flow.id)
                    root.selectedForCopy = true
                    return
                }
                root.require(view.selected.sentBytes === flow.sentBytes, "UI counters differ from backend")
                root.click("xrayNetworkCopy")
                root.require(root.copied === "127.0.0.1:" + root.port, "wrong copied endpoint: " + root.copied)
                root.observed = {"sent": flow.sentBytes, "received": flow.receivedBytes, "copy": true}
                view.search = String(root.port)
                view.scope = "loopback"
                view.protocol = "TCP"
                root.require(view.mapRows.length === 1, "live filters lost the connection")
                root.click("xrayNetworkSort")
                root.require(view.sort === "recent", "sort control failed")
                view.search = ""; view.scope = ""; view.protocol = ""
                root.click("xrayNetworkTab_history")
                root.stage++
            } else if (root.stage === 3) {
                root.require(view.eventRows.some(function(row) { return row.port === root.port && row.kind === "opened" }), "live history missing connection")
                root.click("xrayNetworkTab_sockets")
                root.stage++
            } else if (root.stage === 4) {
                root.require(view.socketRows.some(function(row) { return row.remote === "127.0.0.1:" + root.port }), "live socket endpoint wrong")
                root.click("xrayNetworkMeasurementOptions")
                root.stage = 45
            } else if (root.stage === 45) {
                root.click("xrayNetworkNamesToggle")
                root.stage = 5
            } else if (root.stage === 5) {
                if (!network.resolveNames || !flow || !flow.hostname) { controller.refresh(); return }
                root.require(flow.hostname === root.expectedName, "name differs from system resolver: " + flow.hostname)
                root.require(root.find(drawer, "xrayNetworkNamesToggle").checked, "lookup switch does not reflect enabled state")
                root.observed.nameLookup = true
                root.click("xrayNetworkNamesToggle")
                root.stage++
            } else if (root.stage === 6) {
                root.require(network.resolveNames === false && !flow.hostname, "stop lookup retained names")
                root.require(!root.find(drawer, "xrayNetworkNamesToggle").checked, "lookup switch does not reflect disabled state")
                root.find(drawer, "xrayNetworkInterface").changed("lo")
                root.click("xrayNetworkCaptureToggle")
                root.stage++
            } else if (root.stage === 7) {
                var capture = network.capture || {}
                if (capture.starting) { controller.refresh(); return }
                if (capture.active) {
                    root.require(network.mode === "packets", "live capture did not switch to packet rates")
                    if (!flow || !(flow.sentBytes > 0)) { controller.refresh(); return }
                    root.observed.capture = "live packet rates"
                    root.click("xrayNetworkCaptureToggle")
                    root.stage++
                } else {
                    root.require(!root.captureRequired, "live capture did not start: " + capture.error)
                    root.require(!!capture.error && network.mode === "tcp", "permission failure was not explicit")
                    root.require(root.find(drawer, "xrayNetworkCaptureToggle").text === "Retry capture", "failed capture did not offer retry")
                    root.observed.capture = "live permission failure"
                    root.stage++
                }
            } else if (root.stage === 8) {
                root.require(!network.capture.active && network.mode === "tcp", "capture stop did not restore TCP mode")
                root.click("xrayNetworkTab_map")
                view.toolsVisible = false
                view.choose(flow.id)
                root.stage = 85
            } else if (root.stage === 85) {
                root.click("xrayNetworkInspectOwner")
                root.stage = 9
            } else {
                if (controller.inspectionGeneration === root.originalInspection) return
                root.require(controller.snapshot.target.rootPid === root.targetPid, "owner button inspected wrong process")
                root.require(controller.drawer === "", "owner navigation did not close drawer")
                console.log("XRAY_NETWORK_LIVE " + JSON.stringify(Object.assign(root.observed, {pid: root.targetPid, mode: "tcp", visible: true, owner: true, filters: true, history: true})))
                poll.stop()
                controller.close()
                Qt.quit()
            }
        }
    }
}
