import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import "ui" as XRay
import "ui/drawers" as Drawers

ShellRoot {
    id: root
    property var fixture: JSON.parse(Quickshell.env("XRAY_NETWORK_FIXTURE"))
    property int stage: 0
    property int attempts: 0
    property int inspected: 0
    property string copied: ""
    property string selected: ""
    property var configured: ({})
    property var view
    XRay.XRayTheme { id: theme }
    TestCase { id: driver; when: false }
    function require(value, message) {
        if (value) return
        poll.stop()
        console.log("XRAY_NETWORK_ERROR " + message)
        Qt.exit(1)
        throw new Error(message)
    }
    function descendants(item) {
        var all = [], pending = [item]
        while (pending.length) {
            var next = pending.shift()
            all.push(next)
            if (next.children) pending = pending.concat(next.children.slice())
        }
        return all
    }
    function item(name) { return descendants(drawer).find(function(child) { return child.objectName === name }) }
    function click(name) {
        var button = item(name)
        require(button && button.enabled && button.visible, "button unavailable: " + name)
        driver.mouseClick(button, button.width / 2, button.height / 2)
    }
    function screenshot(name, next) {
        var directory = Quickshell.env("XRAY_NETWORK_SCREENSHOTS")
        if (!directory) { stage = next; return }
        stage = -1
        drawer.grabToImage(function(result) {
            require(result.saveToFile(directory + "/" + name + ".png"), "screenshot failed")
            stage = next
        })
    }
    Window {
        id: window
        width: Number(Quickshell.env("XRAY_NETWORK_WIDTH")) || 820
        height: Number(Quickshell.env("XRAY_NETWORK_HEIGHT")) || 900
        visible: true
        color: theme.panel
        Drawers.DetailDrawer {
            id: drawer
            anchors.fill: parent
            theme: theme
            snapshot: root.fixture
            domain: "connections"
            onProcessSelected: function(pid) { root.inspected = pid; }
            onNetworkOwnerSelected: function(owner) { root.inspected = Number(owner.pid); }
            onCopyRequested: function(text) { root.copied = text; }
            onNetworkConfigured: function(options) { root.configured = options; }
        }
    }
    Timer {
        id: poll
        interval: 40
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
            root.attempts++
            root.require(root.attempts < 180, "timed out at stage " + root.stage)
            if (root.stage === -1) return
            if (root.stage === 0) {
                root.view = root.item("xrayNetworkView")
                root.require(root.view && root.view.visible, "map not opened")
                root.require(root.view.mapRows.length === 6, "missing flow rows")
                root.require(root.item("xrayNetworkList").count === 6, "map not populated")
                root.screenshot("map-" + window.width, 1)
            } else if (root.stage === 1) {
                root.view.search = "8443"
                root.stage++
            } else if (root.stage === 2) {
                root.require(root.view.mapRows.length === 1, "search did not filter endpoints")
                root.view.search = ""
                root.view.scope = "internet"
                root.stage++
            } else if (root.stage === 3) {
                root.require(root.view.mapRows.length === 3, "scope filter wrong")
                root.view.scope = ""
                root.view.protocol = "UDP"
                root.stage++
            } else if (root.stage === 4) {
                root.require(root.view.mapRows.length === 1, "protocol filter wrong")
                root.view.protocol = ""
                root.stage++
            } else if (root.stage === 5) {
                var list = root.item("xrayNetworkList")
                list.forceLayout()
                var row = list.itemAtIndex(0).item
                driver.mouseClick(row, row.width / 2, row.height / 2)
                root.stage++
            } else if (root.stage === 6) {
                root.require(root.view.selected !== null, "flow selection did not show evidence")
                var details = root.item("xrayNetworkEvidence")
                root.require(details.y + details.height <= root.view.height + 1, "details extend below drawer")
                root.selected = root.view.selectedId
                root.click("xrayNetworkCopy")
                root.require(!!root.copied, "copy endpoint failed")
                root.click("xrayNetworkInspectOwner")
                root.require(root.inspected === 42, "owner inspection failed")
                root.screenshot("evidence-" + window.width, 7)
            } else if (root.stage === 7) {
                var focused = root.item("xrayNetworkList").itemAtIndex(0).item
                focused.forceActiveFocus()
                var next = JSON.parse(JSON.stringify(root.fixture))
                next.network.flows[0].sentRate = 321
                drawer.snapshot = next
                root.stage++
            } else if (root.stage === 8) {
                root.require(root.view.selectedId === root.selected, "live refresh lost selection")
                var list = root.item("xrayNetworkList")
                list.forceLayout()
                var focused = list.itemAtIndex(list.currentIndex).item
                root.require(focused.activeFocus, "refresh lost keyboard row focus")
                root.view.selectedId = ""
                driver.keyClick(Qt.Key_Space)
                root.require(root.view.selectedId === root.selected, "Space failed after refresh")
                root.view.selectedId = ""
                list.positionViewAtIndex(5, ListView.Contain)
                list.forceLayout()
                var last = list.itemAtIndex(5).item
                last.forceActiveFocus()
                root.require(list.contentY + list.height >= list.itemAtIndex(5).y + last.height - 1, "focused row clipped")
                root.click("xrayNetworkTab_history")
                root.stage++
            } else if (root.stage === 9) {
                root.require(root.item("xrayNetworkList").count >= 7, "history missing events")
                root.screenshot("history-" + window.width, 10)
            } else if (root.stage === 10) {
                root.click("xrayNetworkTab_sockets")
                root.stage++
            } else if (root.stage === 11) {
                root.require(root.item("xrayNetworkList").count === 6, "socket tab missing records")
                var sockets = root.item("xrayNetworkList")
                var alignedX = null
                for (var i = 0; i < sockets.count; i++) {
                    sockets.positionViewAtIndex(i, ListView.Contain)
                    sockets.forceLayout()
                    var socketRow = sockets.itemAtIndex(i).item
                    var remoteText = root.descendants(socketRow).find(function(child) { return child.objectName === "xraySocketRemote" })
                    var remoteX = remoteText.mapToItem(sockets, 0, 0).x
                    if (alignedX === null) alignedX = remoteX
                    root.require(Math.abs(remoteX - alignedX) < 1, "remote columns move with status length")
                }
                sockets.positionViewAtBeginning()
                root.screenshot("sockets-" + window.width, 12)
            } else if (root.stage === 12) {
                root.click("xrayNetworkMeasurementOptions")
                root.stage++
            } else if (root.stage === 13) {
                var options = root.item("xrayNetworkMeasurementOptions")
                var historyTab = root.item("xrayNetworkTab_history")
                root.require(options.mapToItem(root.view, 0, 0).x > historyTab.mapToItem(root.view, historyTab.width, 0).x + theme.gap * 2, "options looks like another tab")
                root.require(!root.item("xrayNetworkCaptureToggle").enabled, "capture guessed an interface")
                root.item("xrayNetworkInterface").changed("lo")
                root.require(root.item("xrayNetworkCaptureToggle").enabled, "capture control unavailable")
                root.screenshot("options-" + window.width, 14)
            } else if (root.stage === 14) {
                var failed = JSON.parse(JSON.stringify(drawer.snapshot))
                failed.network.capture.error = "Capture helper is unavailable"
                failed.network.capture.errorKind = "missing-helper"
                drawer.snapshot = failed
                root.stage = 140
            } else if (root.stage === 140) {
                root.require(root.item("xrayNetworkCaptureToggle").text === "Retry capture", "capture failure did not offer retry")
                root.require(root.item("xrayNetworkCaptureSummary").rows[0].value.indexOf("Install dumpcap") >= 0, "missing requirement not visible")
                root.screenshot("capture-unavailable-" + window.width, 141)
            } else if (root.stage === 141) {
                var renamed = JSON.parse(JSON.stringify(drawer.snapshot))
                renamed.network.capture = {active: true, interface: "lo", interfaces: []}
                drawer.snapshot = renamed
                root.stage = 142
            } else if (root.stage === 142) {
                root.require(root.view.captureInterface === "", "removed interface still selected")
                root.click("xrayNetworkCaptureToggle")
                root.require(root.configured.capture === false, "active capture cannot stop after interface removal")
                drawer.selectionEnabled = false
                root.require(!root.item("xrayNetworkCaptureToggle").enabled, "offline capture enabled")
                root.require(!root.item("xrayNetworkNamesToggle").enabled, "offline DNS enabled")
                root.click("xrayNetworkLimits")
                root.stage = 15
            } else if (root.stage === 15) {
                root.require(root.item("xrayNetworkCoverageFacts").rows.length === 2, "status is not a short TCP/UDP summary")
                root.require(!root.item("xrayNetworkCoverageTechnical").visible, "technical detail shown by default")
                root.screenshot("status-" + window.width, 16)
            } else if (root.stage === 16) {
                root.click("xrayNetworkCoverageDetails")
                root.stage++
            } else if (root.stage === 17) {
                root.require(root.item("xrayNetworkCoverageTechnical").visible, "technical details cannot expand")
                root.screenshot("status-details-" + window.width, 18)
            } else {
                console.log("XRAY_NETWORK_UI " + JSON.stringify({"map": true, "search": true, "filters": true, "history": true, "sockets": true, "evidence": true, "offline": true, "refresh": true, "width": window.width}))
                poll.stop()
                Qt.quit()
            }
        }
    }
}
