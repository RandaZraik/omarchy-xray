import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "ui" as XRay
import "ui/drawers" as Drawers

ShellRoot {
    id: root

    readonly property string query: Quickshell.env("XRAY_DRAWER_QUERY")
        || "chromium-resource-2999"
    readonly property string snapshotPath: Quickshell.env("XRAY_DRAWER_SNAPSHOT")
    property var snapshot: ({})
    property int typedCharacters: 0
    property double finalTypedAt: 0
    property double clearStartedAt: 0
    property int searchElapsedMs: -1
    property int clearElapsedMs: -1
    property int filteredVisibleCount: -1
    property bool clearing: false
    property int baselineVisibleCount: -1
    property int baselineResourceCount: -1
    property int stableBaselineTicks: 0

    function require(condition, message) {
        if (condition) return
        console.log("XRAY_DRAWER_SEARCH_ERROR " + message)
        window.visible = false
        Qt.quit()
        throw new Error(message)
    }

    function syntheticSnapshot() {
        var files = []
        for (var index = 0; index < 12000; index++) {
            files.push({
                "target": "/tmp/chromium-resource-" + (index % 3000),
                "kind": "file",
                "mode": "read/write",
                "deleted": false,
                "pid": 3377 + (index % 8),
                "fd": index,
                "position": index,
                "flags": "0100002",
                "mountId": 35
            })
        }
        return {"files": files, "locks": []}
    }

    function finish() {
        console.log("XRAY_DRAWER_SEARCH " + JSON.stringify({
            "sourceCount": (snapshot.files || []).length,
            "resourceCount": baselineResourceCount,
            "filteredCount": filteredVisibleCount,
            "restoredCount": drawer.visibleRowCount,
            "searchElapsedMs": searchElapsedMs,
            "clearElapsedMs": clearElapsedMs
        }))
        window.visible = false
        Qt.quit()
    }

    Component.onCompleted: if (!snapshotPath) snapshot = syntheticSnapshot()

    FileView {
        path: root.snapshotPath
        printErrors: !!root.snapshotPath
        onLoaded: root.snapshot = JSON.parse(text())
    }

    XRay.XRayTheme { id: theme }

    PanelWindow {
        id: window
        visible: true
        color: theme.canvas
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        anchors { top: true; bottom: true; left: true; right: true }

        Drawers.DetailDrawer {
            id: drawer
            width: 580
            height: Math.min(800, parent.height)
            anchors.centerIn: parent
            visible: true
            theme: theme
            domain: "files"
            snapshot: root.snapshot
        }
    }

    Timer {
        id: typingTimer
        interval: 8
        repeat: true
        running: false
        onTriggered: {
            root.typedCharacters++
            drawer.queueFilterText(root.query.slice(0, root.typedCharacters))
            if (root.typedCharacters < root.query.length) return
            root.finalTypedAt = Date.now()
            stop()
        }
    }

    Timer {
        interval: 10
        repeat: true
        running: true
        onTriggered: {
            if (!root.finalTypedAt) {
                var resourceCount = drawer.preparedPresentation.rows.length
                var visibleCount = drawer.visibleRowCount
                if (!resourceCount || !visibleCount) return
                if (resourceCount !== root.baselineResourceCount
                        || visibleCount !== root.baselineVisibleCount) {
                    root.baselineResourceCount = resourceCount
                    root.baselineVisibleCount = visibleCount
                    root.stableBaselineTicks = 0
                    return
                }
                root.stableBaselineTicks++
                if (root.stableBaselineTicks < 2) return
                typingTimer.start()
                return
            }
            if (!root.clearing) {
                if (drawer.filterText !== root.query) return
                stop()
                root.filteredVisibleCount = drawer.visibleRowCount
                drawer.grabToImage(function(filteredImage) {
                    root.require(!!filteredImage,
                        "filtered drawer frame could not be rendered")
                    root.searchElapsedMs = Date.now() - root.finalTypedAt
                    root.clearing = true
                    root.clearStartedAt = Date.now()
                    drawer.applyFilterText("")
                    start()
                })
                return
            }
            if (drawer.visibleRowCount !== root.baselineVisibleCount) return
            stop()
            drawer.grabToImage(function(restoredImage) {
                root.require(!!restoredImage,
                    "restored drawer frame could not be rendered")
                root.clearElapsedMs = Date.now() - root.clearStartedAt
                root.finish()
            })
        }
    }

    Timer {
        interval: 30000
        running: true
        onTriggered: root.require(false, "large drawer search benchmark timed out")
    }
}
