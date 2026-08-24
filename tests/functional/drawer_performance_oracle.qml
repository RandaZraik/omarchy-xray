import QtQuick
import Quickshell
import Quickshell.Wayland
import "ui" as XRay
import "ui/drawers" as Drawers

ShellRoot {
    id: root

    property var snapshot: ({})
    property double startedAt: 0
    property int collapseElapsedMs: -1
    property int expandElapsedMs: -1

    function require(condition, message) {
        if (condition) return
        console.log("XRAY_DRAWER_PERF_ERROR " + message)
        window.visible = false
        Qt.quit()
        throw new Error(message)
    }

    function finish() {
        console.log("XRAY_DRAWER_PERF " + JSON.stringify({
            "sourceCount": snapshot.files.length,
            "resourceCount": drawer.preparedPresentation.rows.length,
            "collapsedCount": 1,
            "expandedCount": drawer.visibleRowCount,
            "collapseElapsedMs": collapseElapsedMs,
            "expandElapsedMs": expandElapsedMs
        }))
        window.visible = false
        Qt.quit()
    }

    Component.onCompleted: {
        var files = []
        for (var index = 0; index < 2500; index++) {
            files.push({
                "target": "/tmp/resource-" + (index % 1250),
                "kind": "file",
                "mode": "read/write",
                "deleted": false,
                "pid": 100 + (index % 8),
                "fd": index,
                "position": index,
                "flags": "0100002",
                "mountId": 29
            })
        }
        snapshot = {"files": files, "locks": []}
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
        interval: 20
        repeat: true
        running: true
        onTriggered: {
            if (drawer.preparedPresentation.rows.length !== 1250
                    || drawer.visibleRowCount !== 1251) return
            stop()
            root.startedAt = Date.now()
            drawer.toggleSection("files")
            Qt.callLater(function() {
                root.collapseElapsedMs = Date.now() - root.startedAt
                root.require(drawer.visibleRowCount === 1,
                    "native delegate group did not collapse the section")
                root.startedAt = Date.now()
                drawer.toggleSection("files")
                Qt.callLater(function() {
                    root.expandElapsedMs = Date.now() - root.startedAt
                    root.require(drawer.visibleRowCount === 1251,
                        "native delegate group did not restore the section")
                    root.finish()
                })
            })
        }
    }

    Timer {
        interval: 10000
        running: true
        onTriggered: root.require(false, "large drawer benchmark timed out")
    }
}
