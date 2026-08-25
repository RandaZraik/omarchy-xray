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
    property int collapsedCount: -1
    property string sectionId: ""
    property int expandedCount: 0
    readonly property string drawerDomain: Quickshell.env("XRAY_DRAWER_DOMAIN") || "files"
    readonly property string requestedSection: Quickshell.env("XRAY_DRAWER_SECTION")

    function require(condition, message) {
        if (condition) return
        console.log("XRAY_DRAWER_PERF_ERROR " + message)
        window.visible = false
        Qt.quit()
        throw new Error(message)
    }

    function finish() {
        console.log("XRAY_DRAWER_PERF " + JSON.stringify({
            "sourceCount": (snapshot.files || []).length,
            "resourceCount": drawer.preparedPresentation.rows.length,
            "domain": drawerDomain,
            "section": sectionId,
            "collapsedCount": collapsedCount,
            "expandedCount": drawer.visibleRowCount,
            "collapseElapsedMs": collapseElapsedMs,
            "expandElapsedMs": expandElapsedMs
        }))
        window.visible = false
        Qt.quit()
    }

    function syntheticSnapshot() {
        if (drawerDomain === "runtime") {
            var libraries = []
            for (var libraryIndex = 0; libraryIndex < 180; libraryIndex++)
                libraries.push("/usr/lib/libxray-" + libraryIndex + ".so")
            return {
                "context": {
                    "executable": "/usr/lib/chromium/chromium",
                    "workingDirectory": "/home/demo",
                    "package": {"name": "chromium", "version": "151.0"}
                },
                "security": {
                    "statusAvailable": true,
                    "uid": 1000,
                    "gid": 1000,
                    "groups": [1000],
                    "seccomp": "Disabled",
                    "noNewPrivileges": false,
                    "namespaces": {"mnt": "mnt:[1]", "pid": "pid:[2]"},
                    "capabilitiesKnown": true,
                    "capabilities": [],
                    "limits": [],
                    "libraries": libraries
                },
                "logs": []
            }
        }
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
        return {"files": files, "locks": []}
    }

    Component.onCompleted: snapshot = syntheticSnapshot()

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
            domain: root.drawerDomain
            snapshot: root.snapshot
        }
    }

    Timer {
        interval: 20
        repeat: true
        running: true
        onTriggered: {
            var sections = drawer.preparedPresentation.sections || []
            if (!sections.length || drawer.visibleRowCount < 2) return
            var section = null
            for (var index = 0; index < sections.length; index++) {
                if (root.requestedSection
                        && String(sections[index].id) === root.requestedSection) {
                    section = sections[index]
                    break
                }
                if (!section || sections[index].childCount > section.childCount)
                    section = sections[index]
            }
            if (!section || !section.childCount) return
            stop()
            root.sectionId = String(section.id)
            root.expandedCount = drawer.visibleRowCount
            root.startedAt = Date.now()
            drawer.toggleSection(root.sectionId)
            Qt.callLater(function() {
                root.require(drawer.visibleRowCount
                        === root.expandedCount - section.childCount,
                    "presentation did not collapse the section")
                drawer.grabToImage(function(collapsedImage) {
                    root.require(!!collapsedImage,
                        "collapsed drawer frame could not be rendered")
                    root.collapseElapsedMs = Date.now() - root.startedAt
                    root.collapsedCount = drawer.visibleRowCount
                    root.startedAt = Date.now()
                    drawer.toggleSection(root.sectionId)
                    Qt.callLater(function() {
                        root.require(drawer.visibleRowCount === root.expandedCount,
                            "presentation did not restore the section")
                        drawer.grabToImage(function(expandedImage) {
                            root.require(!!expandedImage,
                                "expanded drawer frame could not be rendered")
                            root.expandElapsedMs = Date.now() - root.startedAt
                            root.finish()
                        })
                    })
                })
            })
        }
    }

    Timer {
        interval: 30000
        running: true
        onTriggered: root.require(false, "large drawer benchmark timed out")
    }
}
