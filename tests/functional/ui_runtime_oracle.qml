import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import "ui" as XRay
import "ui/controllers" as Controllers
import "ui/drawers" as Drawers
import "ui/views" as Views

ShellRoot {
    id: root

    property int stage: 0
    property double deadline: Date.now() + 16000
    property var events: ({})
    property string query: ""
    property int stableTargetPid: 0
    property var samplesBeforeConfigure: []
    property int requestedWidth: Number(Quickshell.env("XRAY_UI_ORACLE_WIDTH")) || 1200
    property int requestedHeight: Number(Quickshell.env("XRAY_UI_ORACLE_HEIGHT")) || 760

    function record(name, value) {
        var next = Object.assign({}, events)
        next[name] = value === undefined ? true : value
        events = next
    }

    function descendants(item) {
        var result = []
        var pending = item && item.children ? item.children.slice() : []
        while (pending.length) {
            var child = pending.shift()
            result.push(child)
            if (child && child.children) pending = pending.concat(child.children)
        }
        return result
    }

    function find(item, propertyName, value) {
        return descendants(item).find(function(child) {
            return child && child[propertyName] !== undefined
                && String(child[propertyName]) === String(value)
        })
    }

    function require(condition, message) {
        if (!condition) {
            console.log("XRAY_UI_ERROR " + message)
            controller.close()
            window.visible = false
            Qt.quit()
            throw new Error(message)
        }
    }

    function insideViewport(item) {
        var point = item.mapToItem(window.contentItem, 0, 0)
        return point.x >= -1 && point.y >= -1
            && point.x + item.width <= window.width + 1
            && point.y + item.height <= window.height + 1
    }

    function finish() {
        console.log("XRAY_UI_RUNTIME " + JSON.stringify({
            "events": events,
            "targetPid": Number((controller.snapshot.target || {}).ownerPid || 0),
            "processRows": processDrawer.allRows.length,
            "filteredRows": processDrawer.rows.length,
            "grid": [dashboard.width, dashboard.height],
            "headerHeight": header.height,
            "footerHeight": footer.height,
            "fontFamily": theme.bodyFont
        }))
        controller.close()
        window.visible = false
        Qt.quit()
    }

    XRay.XRayTheme { id: theme }

    Controllers.XRayController { id: controller }

    PanelWindow {
        id: window
        visible: true
        color: theme.transparent
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
        anchors { top: true; bottom: true; left: true; right: true }

        Item {
            id: testSurface
            width: Math.min(root.requestedWidth, window.width)
            height: Math.min(root.requestedHeight, window.height)
            anchors.centerIn: parent

            Rectangle { anchors.fill: parent; color: theme.canvas }
        }

        ColumnLayout {
            parent: testSurface
            anchors.fill: parent
            anchors.margins: 12
            spacing: theme.smallGap

            Views.AppHeader {
                id: header
                theme: theme
                capabilities: controller.capabilities
                snapshot: controller.snapshot
                interactionEnabled: !controller.interactionBlocked
                onBrowserRequested: root.record("browser")
                onPickRequested: root.record("pick")
                onPauseRequested: root.record("pause")
                onCapsuleRequested: root.record("capsule")
                onSettingsRequested: root.record("settings")
                onCloseRequested: root.record("close")
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                Views.TargetBrowser {
                    id: targetBrowser
                    z: 2
                    width: theme.targetBrowserWidth
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    theme: theme
                    catalog: controller.catalog
                    target: controller.snapshot.target || ({})
                    currentQuery: root.query
                    interactionEnabled: !controller.interactionBlocked
                    closable: false
                    onSelected: function(value) { root.record("search", value) }
                    onCatalogRequested: root.record("catalog")
                }

                ColumnLayout {
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.leftMargin: targetBrowser.width + theme.smallGap
                    spacing: theme.smallGap

                    Views.IdentityBar {
                        Layout.fillWidth: true
                        theme: theme
                        snapshot: controller.snapshot
                        performanceSamples: controller.performanceSamples
                        performanceWindowSeconds: controller.performanceWindowSeconds
                    }

                    Views.DashboardGrid {
                        id: dashboard
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        theme: theme
                        snapshot: controller.snapshot
                        onProcessSelected: function(pid) { root.record("process", pid) }
                        onDetailsRequested: function(domain) { root.record("details", domain) }
                    }

                    Views.FooterBar {
                        id: footer
                        Layout.fillWidth: true
                        theme: theme
                        snapshot: controller.snapshot
                        actionsEnabled: !controller.interactionBlocked
                        onResetRequested: root.record("baseline")
                        onActionRequested: function(action) { root.record("action", action.id) }
                    }
                }
            }
        }

        Drawers.DetailDrawer {
            id: processDrawer
            parent: testSurface
            visible: false
            width: 520
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            theme: theme
            snapshot: controller.snapshot
            domain: "processes"
        }

        Drawers.DetailDrawer {
            id: overflowDrawer
            parent: testSurface
            visible: false
            width: 520
            height: 260
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            theme: theme
            domain: "processes"
        }

        Drawers.SettingsDrawer {
            id: settingsDrawer
            parent: testSurface
            visible: false
            width: 440
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            theme: theme
            schema: controller.settingsSpec
            defaults: controller.defaultSettings
            onApplied: function(values) { root.record("applied", values.refreshSeconds) }
        }

        Drawers.CapsuleDrawer {
            id: capsuleDrawer
            parent: testSurface
            visible: false
            width: 440
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            theme: theme
            capsulePath: "/tmp/example.xray.zip"
            onExportRequested: root.record("export")
            onReportRequested: root.record("report")
            onOpenRequested: function(path) { root.record("open", path) }
            onCompareRequested: function(path) { root.record("compare", path) }
        }

        Views.ConfirmationOverlay {
            id: confirmation
            parent: testSurface
            visible: false
            anchors.fill: parent
            theme: theme
            action: ({"id": "terminate", "label": "Terminate process"})
            onCancelled: root.record("cancel")
            onConfirmed: function(actionId) { root.record("confirmed", actionId) }
        }

        Views.TargetBrowser {
            id: navigationBrowser
            parent: testSurface
            visible: false
            width: theme.targetBrowserWidth
            height: 500
            theme: theme
            currentQuery: ""
            onSelected: function(value) { root.record("ownerSearch", value) }
        }
    }

    Timer {
        interval: 50
        repeat: true
        running: true
        onTriggered: {
            if (Date.now() > root.deadline)
                root.require(false, "UI runtime oracle timed out at stage " + root.stage)
            if (root.stage === 0) {
                root.query = Quickshell.env("XRAY_UI_ORACLE_QUERY")
                root.require(root.query, "target query environment value is required")
                controller.open(JSON.stringify({"query": root.query}))
                root.stage = 1
                return
            }
            if (root.stage === 1) {
                if (controller.busy || !(controller.snapshot.target || {}).rootPid) return
                root.require(dashboard.width > 700 && dashboard.height > 400,
                    "dashboard did not receive a usable layout: "
                        + dashboard.width + "x" + dashboard.height)
                root.require(header.x >= 0 && header.x + header.width <= window.width,
                    "header escaped the responsive viewport")
                root.require(footer.x >= 0 && footer.x + footer.width <= window.width,
                    "footer escaped the responsive viewport")
                ;[
                    "xrayIdentityRail", "xrayCauseCard", "xrayProcessCard",
                    "xrayConnectionsCard", "xrayFilesCard",
                    "xrayDevicesCard", "xrayRuntimeCard", "xrayExplanationsCard"
                ].forEach(function(name) {
                    var card = root.find(window.contentItem, "objectName", name)
                    root.require(card && root.insideViewport(card),
                        name + " escaped the responsive viewport")
                })
                var identityRail = root.find(
                    window.contentItem, "objectName", "xrayIdentityRail"
                )
                ;["CPU", "MEM", "DISK I/O", "GPU", "UPTIME"].forEach(function(label) {
                    root.require(root.find(identityRail, "text", label),
                        "identity rail is missing its " + label + " readout")
                })
                root.require(header.height === 42, "header height changed")
                root.require(footer.height === 38, "footer height changed")

                targetBrowser.catalog = {
                    "quickTargets": [{"label": "Microphone", "query": "microphone"}],
                    "processes": [{
                        "name": "xray-truth",
                        "pid": controller.snapshot.target.ownerPid,
                        "query": "pid:" + controller.snapshot.target.ownerPid
                    }],
                    "limited": ["Process catalog is limited"]
                }
                root.require(targetBrowser.targetCount === 1,
                    "shortcut actions leaked into the target count")
                root.require(targetBrowser.shortcutCount === 1,
                    "quick inspect shortcuts were not counted separately")
                root.require(targetBrowser.catalogLimited,
                    "catalog truncation was not exposed in the browser")
                var limitedLabel = root.find(targetBrowser, "text", "LIMITED")
                root.require(limitedLabel && limitedLabel.visible,
                    "catalog truncation was not rendered in the browser header")
                var expandedBrowserRows = targetBrowser.rows.length
                targetBrowser.toggleGroup("QUICK INSPECT")
                root.require(targetBrowser.isGroupCollapsed("QUICK INSPECT"),
                    "target group did not collapse")
                root.require(targetBrowser.rows.length === expandedBrowserRows - 1,
                    "collapsed target group did not hide its rows")
                root.require(targetBrowser.rows.some(function(row) {
                    return row.rowType === "section"
                        && row.label === "QUICK INSPECT" && row.count === 1
                }), "collapsed target group lost its header or count")
                targetBrowser.toggleGroup("QUICK INSPECT")
                root.require(!targetBrowser.isGroupCollapsed("QUICK INSPECT")
                        && targetBrowser.rows.length === expandedBrowserRows,
                    "target group did not expand back to its complete contents")
                targetBrowser.synchronizeQuery("xray-truth")
                targetBrowser.focusSearch(true)
                var searchField = root.find(targetBrowser, "objectName", "xrayTargetSearchField")
                root.require(searchField && searchField.activeFocus,
                    "the search field did not receive keyboard focus")
                root.require(searchField.selectedText === "xray-truth",
                    "select-all did not select the complete search query")
                controller.refreshInFlight = true
                root.require(targetBrowser.interactionEnabled && searchField.enabled,
                    "background refresh disabled the search field")
                root.require(searchField.activeFocus
                        && searchField.selectedText === "xray-truth",
                    "background refresh discarded search focus or selection")
                root.require(targetBrowser.searchMatches.length === 1,
                    "the target browser did not expose its known match")
                root.require(targetBrowser.acceptCurrent(),
                    "keyboard target acceptance failed")
                root.require(targetBrowser.queryText === "xray-truth",
                    "selecting a target replaced the browser filter")

                navigationBrowser.synchronizeQuery(":9000")
                navigationBrowser.currentQuery = ":9000"
                navigationBrowser.target = {
                    "inspectionId": 9000,
                    "kind": "port",
                    "value": "9000",
                    "ownerPid": 10,
                    "alternatives": [
                        {"pid": 10, "label": "One"},
                        {"pid": 11, "label": "Two"},
                        {"pid": 12, "label": "Three"}
                    ]
                }
                root.require(navigationBrowser.ownerMatches.length === 3,
                    "shared-port owners were not kept together")
                navigationBrowser.choose(navigationBrowser.ownerMatches[1])
                navigationBrowser.currentQuery = "pid:11"
                navigationBrowser.target = {
                    "inspectionId": 9001,
                    "kind": "window-point",
                    "value": "120,240",
                    "query": "window:0xabc",
                    "ownerPid": 12
                }
                root.require(navigationBrowser.stableTargetQuery === "window:0xabc",
                    "resolved target query did not replace stale navigation state")
                navigationBrowser.target = {
                    "inspectionId": 9001,
                    "kind": "process",
                    "value": "11",
                    "ownerPid": 11,
                    "alternatives": [{"pid": 11, "label": "Two"}]
                }
                root.require(navigationBrowser.queryText === ":9000"
                        && navigationBrowser.ownerMatches.length === 3,
                    "owner navigation discarded its original result set")

                ;[
                    ["search", "browser"],
                    ["pick", "pick"],
                    ["pause", "pause"],
                    ["capsule", "capsule"],
                    ["settings", "settings"],
                    ["close", "close"]
                ].forEach(function(spec) {
                    var button = root.find(header, "iconName", spec[0])
                    root.require(button, "missing header control: " + spec[0])
                    button.clicked()
                })

                var baseline = root.find(footer, "tooltipText", "Start a new comparison baseline")
                root.require(baseline, "missing baseline control")
                baseline.clicked()
                var pauseAction = root.find(footer, "text", "Pause process")
                root.require(pauseAction && pauseAction.enabled,
                    "background refresh disabled the process action button")
                controller.refreshInFlight = false
                pauseAction.clicked()

                processDrawer.visible = true
                processDrawer.filterText = "xray-truth"
                root.require(processDrawer.allRows.length >= 1, "process drawer is empty")
                root.require(processDrawer.rows.length >= 1, "drawer filter hid its exact match")

                var overflowRows = []
                for (var rowIndex = 0; rowIndex < 80; rowIndex++)
                    overflowRows.push({
                        "pid": 9000 + rowIndex,
                        "name": "overflow-" + rowIndex,
                        "command": ["worker", String(rowIndex)],
                        "cpuPercent": rowIndex,
                        "memoryBytes": 1024
                    })
                overflowDrawer.snapshot = {"processes": overflowRows}
                overflowDrawer.visible = true
                var scrollView = root.descendants(overflowDrawer).find(function(item) {
                    return item && item.objectName === "xrayProcessEvidenceRows"
                        && item.height > 0
                })
                root.require(scrollView && scrollView.contentHeight > scrollView.height,
                    "overflow drilldown did not expose real scrolling")
                scrollView.contentY = scrollView.contentHeight - scrollView.height
                root.require(scrollView.contentY > 0,
                    "overflow drilldown could not scroll to its final row")
                overflowDrawer.visible = false

                settingsDrawer.visible = true
                settingsDrawer.openWith(controller.currentSettings)
                var savedRefresh = settingsDrawer.draft.refreshSeconds
                settingsDrawer.updateDraft("refreshSeconds", savedRefresh === 1 ? 2 : 1)
                settingsDrawer.openWith(controller.currentSettings)
                root.require(settingsDrawer.draft.refreshSeconds === savedRefresh,
                    "unsaved settings survived reopening")
                var defaultsButton = root.find(settingsDrawer, "text", "Restore defaults")
                var applyButton = root.find(settingsDrawer, "text", "Apply settings")
                root.require(defaultsButton && applyButton, "settings actions are missing")
                defaultsButton.clicked()
                applyButton.clicked()

                capsuleDrawer.visible = true
                ;[
                    ["Export private report", "export"],
                    ["Copy redacted text report", "report"],
                    ["Open report", "open"],
                    ["Compare with current", "compare"]
                ].forEach(function(spec) {
                    var button = root.find(capsuleDrawer, "text", spec[0])
                    root.require(button, "missing capsule action: " + spec[0])
                    button.clicked()
                })

                confirmation.visible = true
                var cancelButton = root.find(confirmation, "text", "Cancel")
                var confirmButton = root.find(confirmation, "text", "Terminate process")
                root.require(cancelButton && confirmButton, "confirmation actions are missing")
                cancelButton.clicked()
                confirmButton.clicked()
                root.samplesBeforeConfigure = controller.performanceSamples.slice()
                controller.configure({
                    "refreshSeconds": 1,
                    "historySeconds": 60,
                    "capturePreview": false
                })
                root.stage = 2
                return
            }
            if (root.stage === 2) {
                if (controller.busy || controller.refreshInFlight
                        || Number(controller.currentSettings.refreshSeconds) !== 1)
                    return
                root.require(controller.refreshIntervalMs === 1000,
                    "the saved refresh setting did not update the live timer")
                root.require(controller.performanceSamples.length
                        > root.samplesBeforeConfigure.length,
                    "changing refresh cadence discarded or failed to append performance history")
                root.require(controller.performanceSamples.slice(
                        0, root.samplesBeforeConfigure.length
                    ).every(function(sample, index) {
                        return Number(sample.capturedAt)
                            === Number(root.samplesBeforeConfigure[index].capturedAt)
                    }), "changing refresh cadence rewrote existing performance timestamps")
                root.require(controller.performanceSamples.every(function(sample, index, rows) {
                    return Number(sample.capturedAt) > 0
                        && (index === 0
                            || Number(sample.capturedAt) >= Number(rows[index - 1].capturedAt))
                }), "performance history timestamps are missing or unordered")
                controller.toggleSampling()
                root.stage = 3
                return
            }
            if (root.stage === 3) {
                if (controller.snapshot.samplingPaused !== true) return
                root.record("samplingPaused")
                controller.toggleSampling()
                root.stage = 4
                return
            }
            if (root.stage === 4) {
                if (controller.snapshot.samplingPaused === true) return
                root.record("samplingResumed")
                controller.requestCatalog(true)
                root.stage = 5
                return
            }
            if (root.stage === 5) {
                if (controller.catalogRequested || !(controller.catalog.processes || []).length)
                    return
                root.record("catalogBackend")
                root.stableTargetPid = Number((controller.snapshot.target || {}).ownerPid || 0)
                controller.openCapsule("/definitely/missing/xray-capsule.zip")
                root.stage = 6
                return
            }
            if (root.stage === 6) {
                if (controller.busy) return
                root.require(controller.notice !== "",
                    "request-specific backend error produced no visible feedback")
                root.require(Number((controller.snapshot.target || {}).ownerPid || 0)
                    === root.stableTargetPid,
                    "failed capsule import replaced the current inspection")
                root.record("callbackError")
                ;["catalog", "pick", "pause", "capsule", "settings", "close",
                   "browser", "baseline", "action", "search", "ownerSearch",
                   "applied", "export", "report",
                   "open", "compare", "cancel", "confirmed", "samplingPaused",
                   "samplingResumed", "catalogBackend", "callbackError"].forEach(function(name) {
                    root.require(root.events[name] !== undefined, "control emitted no signal: " + name)
                })
                root.require(root.events.search === "pid:" + controller.snapshot.target.ownerPid,
                    "target browser accepted the wrong query")
                root.require(root.events.ownerSearch === "pid:11",
                    "shared-port owner navigation selected the wrong process")
                root.require(root.events.action === "pause", "footer dispatched the wrong action")
                root.require(root.events.confirmed === "terminate",
                    "confirmation dispatched the wrong action")
                root.finish()
            }
        }
    }
}
