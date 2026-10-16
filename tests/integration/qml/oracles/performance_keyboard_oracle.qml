import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import "ui" as XRay
import "ui/drawers" as Drawers
import "ui/DetailDomains.js" as DetailDomains

ShellRoot {
    id: root
    property int stage: 0
    property int attempts: 0
    property int tabs: 0
    property var visited: ({})
    property real furthestScroll: 0
    property var list: null
    property string selectedId: ""
    property var searchField: null
    property var detailsTab: null
    property var overviewTab: null

    XRay.XRayTheme { id: theme }
    TestCase { id: driver; when: false }

    function require(value, message) {
        if (value) return
        console.log("XRAY_PERFORMANCE_KEYBOARD_ERROR " + message)
        Qt.exit(1)
        throw new Error(message)
    }

    function descendants(item) {
        var result = [item]
        for (var index = 0; index < (item.children || []).length; index++)
            result = result.concat(descendants(item.children[index]))
        return result
    }

    function focusedRow() {
        var item = window.activeFocusItem
        while (item && item !== list) {
            if (item.rowData !== undefined) return item
            item = item.parent
        }
        return null
    }

    function focusSelected() {
        var index = drawer.displayRows.findIndex(function(row) {
            return row.findingId === root.selectedId
        })
        root.require(index >= 0, "selected measurement disappeared")
        list.positionViewAtIndex(index, ListView.Contain)
        list.forceLayout()
        var delegate = list.itemAtIndex(index)
        root.require(delegate && delegate.item, "selected measurement was not instantiated")
        delegate.item.focusHeader()
    }

    function refreshSnapshot() {
        var next = JSON.parse(JSON.stringify(drawer.snapshot))
        next.performance.checks[0].title = "Keyboard refresh " + root.stage
        drawer.snapshot = next
    }

    Window {
        id: window
        width: 620
        height: 600
        visible: true
        color: theme.panel

        Drawers.DetailDrawer {
            id: drawer
            anchors.fill: parent
            theme: theme
            domain: DetailDomains.Performance
            snapshot: JSON.parse(Quickshell.env("XRAY_PERFORMANCE_FIXTURE"))
        }
    }

    Timer {
        interval: 40
        running: true
        repeat: true
        property bool advancing: false
        onTriggered: {
            // QtTest key events can process another timer tick before a step finishes.
            if (advancing) return
            advancing = true
            try { advance() } finally { advancing = false }
        }
        function advance() {
            root.attempts++
            root.require(root.attempts < 180, "timeout at stage " + root.stage)
            if (root.stage === 0) {
                drawer.selectPerformanceTab(true)
                root.stage++
            } else if (root.stage === 1) {
                var items = root.descendants(drawer)
                root.list = items.find(function(item) {
                    return item.visible && typeof item.positionViewAtIndex === "function"
                        && item.model && item.model.length === drawer.displayRows.length
                })
                root.require(root.list && root.list.contentHeight > root.list.height, "fixture does not require scrolling")
                root.searchField = items.find(function(item) { return item.placeholderText === "Search measurements…" })
                root.detailsTab = items.find(function(item) { return item.objectName === "xrayPerformanceDetailsToggle" })
                root.overviewTab = items.find(function(item) { return item.objectName === "xrayPerformanceOverviewTab" })
                root.require(root.searchField && root.detailsTab && root.overviewTab, "keyboard controls missing")
                root.selectedId = drawer.allRows[0].findingId
                root.focusSelected()
                root.stage++
            } else if (root.stage === 2) {
                var focused = root.focusedRow()
                if (focused) {
                    var button = window.activeFocusItem
                    var position = button.mapToItem(root.list, 0, 0)
                    root.require(position.y >= -1 && position.y + button.height <= root.list.height + 1,
                        "Tab focused an offscreen row: " + drawer.performanceRowKey(focused.rowData))
                    root.visited[drawer.performanceRowKey(focused.rowData)] = true
                    root.furthestScroll = Math.max(root.furthestScroll, root.list.contentY)
                }
                if (Object.keys(root.visited).length === drawer.displayRows.length) {
                    root.require(root.furthestScroll > 0, "keyboard traversal never scrolled")
                    root.focusSelected()
                    root.stage++
                } else {
                    root.tabs++
                    root.require(root.tabs < 100, "Tab did not reach every measurement and section")
                    driver.keyClick(Qt.Key_Tab)
                }
            } else if (root.stage === 3) {
                driver.keyClick(Qt.Key_Space)
                root.stage++
            } else if (root.stage === 4) {
                root.require(drawer.expandedChecks[root.selectedId] === true, "Space did not expand the measurement")
                root.refreshSnapshot()
                root.stage++
            } else if (root.stage === 5) {
                var restored = root.focusedRow()
                root.require(restored && restored.rowData.findingId === root.selectedId,
                    "refresh lost the focused measurement")
                root.require(typeof window.activeFocusItem.clicked === "function", "refresh focused a noninteractive loader")
                driver.keyClick(Qt.Key_Space)
                root.stage++
            } else if (root.stage === 6) {
                root.require(drawer.expandedChecks[root.selectedId] === false, "Space stopped working after refresh")
                root.refreshSnapshot()
                root.searchField.forceActiveFocus(Qt.TabFocusReason)
                root.stage++
            } else if (root.stage === 7) {
                root.require(root.searchField.activeFocus, "pending refresh stole focus from search")
                root.focusSelected()
                root.refreshSnapshot()
                root.detailsTab.forceActiveFocus(Qt.TabFocusReason)
                root.stage++
            } else if (root.stage === 8) {
                root.require(root.detailsTab.activeFocus, "pending refresh stole focus from the measurements tab")
                root.overviewTab.forceActiveFocus(Qt.TabFocusReason)
                driver.keyClick(Qt.Key_Space)
                root.refreshSnapshot()
                root.stage++
            } else {
                root.require(!drawer.technicalDetails && root.overviewTab.activeFocus,
                    "refresh stole focus from the overview tab")
                console.log("XRAY_PERFORMANCE_KEYBOARD " + JSON.stringify({
                    visitedRows: Object.keys(root.visited).length,
                    scrolled: root.furthestScroll > 0,
                    expanded: true,
                    refreshed: true,
                    searchFocus: true,
                    tabFocus: true
                }))
                Qt.quit()
            }
        }
    }
}
