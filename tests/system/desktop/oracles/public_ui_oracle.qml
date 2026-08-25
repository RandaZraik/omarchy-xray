import QtQuick
import Quickshell
import "." as Plugin

ShellRoot {
    id: root

    property int stage: 0
    // This exercises every live drawer plus process actions and capsule I/O.
    // Leave headroom for loaded desktop machines; stage assertions still fail
    // immediately when behavior is wrong.
    property double deadline: Date.now() + 75000
    property string query: ""
    property string expectedPath: ""
    property int expectedPid: 0
    property int expectedChildPid: 0
    property int expectedPort: 0
    property string capsulePath: ""
    property var controller: null
    property var dashboard: null
    property var header: null
    property var browser: null
    property var footer: null
    property var settingsDrawer: null
    property var capsuleDrawer: null
    property var detailDrawer: null
    property var panel: null
    property bool expectPanelStable: false
    property int unexpectedPanelHides: 0
    property real dashboardY: 0
    property real dashboardHeight: 0
    property int drilldownIndex: 0
    property var drilldowns: [
        {"card": "xrayCauseCard", "domain": "cause"},
        {"card": "xrayProcessCard", "domain": "processes"},
        {"card": "xrayConnectionsCard", "domain": "connections"},
        {"card": "xrayFilesCard", "domain": "files"},
        {"card": "xrayDevicesCard", "domain": "devices"},
        {"card": "xrayRuntimeCard", "domain": "runtime"},
        {"card": "xrayExplanationsCard", "domain": "explanations"}
    ]
    property var events: ({})

    function record(name, value) {
        var next = Object.assign({}, events)
        next[name] = value
        events = next
    }

    function childrenOf(object) {
        var result = []
        function append(values) {
            if (!values) return
            for (var index = 0; index < values.length; index++) {
                var value = values[index]
                if (value && result.indexOf(value) < 0) result.push(value)
            }
        }
        append(object && object.data)
        append(object && object.children)
        if (object && object.contentItem && result.indexOf(object.contentItem) < 0)
            result.push(object.contentItem)
        return result
    }

    function descendants(object) {
        var result = []
        var pending = childrenOf(object)
        while (pending.length) {
            var child = pending.shift()
            if (!child || result.indexOf(child) >= 0) continue
            result.push(child)
            pending = pending.concat(childrenOf(child))
        }
        return result
    }

    function named(name) {
        return [entry, barEntry].concat(descendants(entry), descendants(barEntry)).find(
            function(object) { return String(object.objectName || "") === name }
        )
    }

    function findProperty(object, propertyName, value) {
        return [object].concat(descendants(object)).find(function(candidate) {
            return candidate && candidate[propertyName] !== undefined
                && String(candidate[propertyName]) === String(value)
        })
    }

    function textDump(object) {
        return [object].concat(descendants(object)).filter(function(candidate) {
            return candidate && candidate.text !== undefined && candidate.visible !== false
        }).map(function(candidate) { return String(candidate.text) }).join("\n")
    }

    function require(condition, message) {
        if (condition) return
        console.log("XRAY_PUBLIC_UI_ERROR " + message)
        entry.close()
        Qt.quit()
        throw new Error(message)
    }

    function cardInsideDashboard(card) {
        var point = card.mapToItem(dashboard, 0, 0)
        return point.x >= -1 && point.y >= -1
            && point.x + card.width <= dashboard.width + 1
            && point.y + card.height <= dashboard.height + 1
    }

    function finish() {
        console.log("XRAY_PUBLIC_UI " + JSON.stringify({
            "events": events,
            "targetPid": Number((controller.snapshot.target || {}).ownerPid || 0),
            "offline": controller.offline,
            "grid": [dashboard.width, dashboard.height],
            "capsulePath": capsulePath,
            "inspectionId": Number((controller.snapshot.target || {}).inspectionId || 0)
        }))
        entry.close()
        Qt.quit()
    }

    QtObject {
        id: shellStub
        function toggle(moduleName, payloadJson) {
            root.record("barModule", moduleName)
            root.record("barPayload", payloadJson)
        }
    }

    QtObject {
        id: barStub
        property var shell: shellStub
        property bool vertical: false
        property int barSize: 30
        property string fontFamily: "monospace"
        property color barForeground: "#eeeeee"
        property color urgent: "#ff8888"
        property bool foregroundAnimationEnabled: false
        function showTooltip(item, text) {}
        function hideTooltip(item) {}
        function registerClickTarget(item) {}
        function unregisterClickTarget(item) {}
    }

    Plugin.BarWidget {
        id: barEntry
        bar: barStub
    }

    Plugin.XRay { id: entry }

    Connections {
        target: root.panel
        function onVisibleChanged() {
            if (root.expectPanelStable && root.panel && !root.panel.visible)
                root.unexpectedPanelHides += 1
        }
    }

    Timer {
        interval: 60
        repeat: true
        running: true
        onTriggered: {
            if (Date.now() > root.deadline) {
                console.log("XRAY_PUBLIC_UI_STATE " + JSON.stringify({
                    "stage": root.stage,
                    "drilldownIndex": root.drilldownIndex,
                    "drilldown": root.drilldowns[root.drilldownIndex] || {},
                    "controller": !!root.controller,
                    "drawer": root.controller ? root.controller.drawer : null,
                    "detailDomain": root.controller ? root.controller.detailDomain : null,
                    "busy": root.controller ? root.controller.busy : null,
                    "refreshInFlight": root.controller
                        ? root.controller.refreshInFlight : null,
                    "capturingPreview": root.controller
                        ? root.controller.capturingPreview : null,
                    "notice": root.controller ? root.controller.notice : "",
                    "target": root.controller
                        ? (root.controller.snapshot.target || {}) : {},
                    "catalogRequested": root.controller
                        ? root.controller.catalogRequested : null,
                    "browserVisible": root.browser ? root.browser.visible : null,
                    "catalogProcesses": root.controller
                        ? (root.controller.catalog.processes || []).length : null
                }))
                root.require(false, "public UI oracle timed out at stage " + root.stage)
            }

            if (root.stage === 0) {
                root.query = Quickshell.env("XRAY_UI_ORACLE_QUERY")
                root.expectedPath = Quickshell.env("XRAY_UI_ORACLE_PATH")
                root.expectedPid = Number(Quickshell.env("XRAY_UI_ORACLE_PID"))
                root.expectedChildPid = Number(Quickshell.env("XRAY_UI_ORACLE_CHILD_PID"))
                root.expectedPort = Number(Quickshell.env("XRAY_UI_ORACLE_PORT"))
                root.require(root.query && root.expectedPid > 0, "truth environment is missing")
                var launcher = root.named("xrayBarLauncher")
                root.require(launcher, "the shipped bar launcher was not created")
                launcher.pressed(Qt.LeftButton)
                root.require(root.events.barModule === "io.github.randazraik.xray",
                    "bar launcher sent the wrong module")
                root.require(root.events.barPayload === "{}",
                    "bar launcher sent the wrong payload")
                entry.open(JSON.stringify({"query": root.query}))
                root.stage = 1
                return
            }

            if (root.stage === 1) {
                root.controller = root.named("xrayController")
                root.dashboard = root.named("xrayDashboard")
                root.header = root.named("xrayAppHeader")
                root.browser = root.named("xrayTargetBrowser")
                root.footer = root.named("xrayFooter")
                root.settingsDrawer = root.named("xraySettingsDrawer")
                root.capsuleDrawer = root.named("xrayCapsuleDrawer")
                root.detailDrawer = root.named("xrayDetailDrawer")
                root.panel = root.named("xrayPanel")
                if (!root.controller || root.controller.busy
                        || !((root.controller.snapshot.target || {}).rootPid)) return
                root.require(root.dashboard && root.header && root.browser && root.footer,
                    "the shipped dashboard composition is incomplete")
                var targetSearch = root.named("xrayTargetSearchField")
                root.require(targetSearch && targetSearch.visible,
                    "the pinned target search is not visible")
                root.require(root.settingsDrawer && root.capsuleDrawer && root.detailDrawer,
                    "the shipped drawers are incomplete")
                root.require(root.panel && root.panel.visible,
                    "the shipped inspection panel is not visible")
                var backdrop = root.named("xrayBackdropDismissArea")
                root.require(backdrop,
                    "the production outside-click dismiss target is missing")
                // The oracle runs on the user's live desktop. Ignore unrelated
                // physical clicks while it drives controls directly.
                backdrop.enabled = false
                root.require(Number(root.controller.snapshot.target.ownerPid) === root.expectedPid,
                    "the public UI inspected the wrong process")
                root.require(Number(root.controller.snapshot.target.inspectionId) > 0,
                    "the public UI has no action identity binding")
                root.require(root.dashboard.width > 900 && root.dashboard.height > 500,
                    "the dashboard did not receive a usable panel layout")

                var cardNames = [
                    "xrayCauseCard", "xrayProcessCard",
                    "xrayConnectionsCard", "xrayFilesCard",
                    "xrayDevicesCard", "xrayRuntimeCard", "xrayExplanationsCard"
                ]
                cardNames.forEach(function(name) {
                    var card = root.named(name)
                    root.require(card && card.visible, "missing visible production card: " + name)
                    root.require(card.width > 0 && card.height > 0,
                        "production card has no geometry: " + name)
                    root.require(root.cardInsideDashboard(card),
                        "production card escapes the dashboard: " + name)
                })

                var identityRail = root.named("xrayIdentityRail")
                root.require(identityRail && identityRail.visible
                        && identityRail.width > 0 && identityRail.height > 0,
                    "the production identity rail is missing")
                var telemetryTrace = root.named("xrayTelemetryTrace")
                root.require(telemetryTrace && telemetryTrace.visible
                        && telemetryTrace.width >= telemetryTrace.theme.telemetryTraceMinimumWidth
                        && telemetryTrace.height > 0,
                    "the production 60-second telemetry trace is missing")

                var processCard = root.named("xrayProcessCard")
                var processText = root.textDump(processCard)
                root.require(processText.indexOf("xray-truth") >= 0,
                    "process card does not render the independently known root")
                root.require(processText.indexOf("PID " + root.expectedPid) >= 0,
                    "process card does not render the independently known PID")
                root.require(processCard.snapshot.processes.some(function(row) {
                    return Number(row.pid) === root.expectedChildPid
                }), "process card model omits the independently known child")

                var connectionsCard = root.named("xrayConnectionsCard")
                root.require(connectionsCard.rows.some(function(row) {
                    return Number(row.localPort) === root.expectedPort && row.listening === true
                }), "connections card model omits the independently known listener")
                root.require(root.textDump(connectionsCard).indexOf(String(root.expectedPort)) >= 0,
                    "connections card does not render its known listener")

                var filesCard = root.named("xrayFilesCard")
                root.require(filesCard.rows.some(function(row) {
                    return String(row.target).replace(/ \(deleted\)$/, "") === root.expectedPath
                }), "files card model omits the independently known locked file")
                root.require(Number((root.controller.snapshot.metrics || {}).processCount)
                    === root.controller.snapshot.processes.length,
                    "performance card process count disagrees with its process model")

                root.dashboardY = root.dashboard.y
                root.dashboardHeight = root.dashboard.height
                var ctrlK = root.findProperty(entry, "sequence", "Ctrl+K")
                root.require(ctrlK, "production Ctrl+K shortcut is missing")
                ctrlK.activated()
                root.stage = 2
                return
            }

            if (root.stage === 2) {
                if (root.controller.catalogRequested
                        || !(root.controller.catalog.processes || []).length) return
                root.require(root.dashboard.y === root.dashboardY
                    && root.dashboard.height === root.dashboardHeight,
                    "opening the target browser changed the pinned dashboard geometry")
                root.browser.synchronizeQuery("xray-truth")
                root.require(root.browser.searchMatches.length >= 1,
                    "production target browser has no live process match")
                root.expectPanelStable = true
                root.require(root.browser.acceptCurrent(),
                    "production target browser could not accept its exact match")
                root.stage = 20
                return
            }

            if (root.stage === 20) {
                root.require(!root.controller.capturingPreview,
                    "accepted search hid X-Ray to recapture its preview")
                if (root.controller.busy) return
                root.require(root.panel.visible && root.unexpectedPanelHides === 0,
                    "accepted search hid the inspection panel")
                root.expectPanelStable = false
                root.require(root.browser.queryText === "xray-truth",
                    "accepted search replaced the original browser filter")
                root.require(Number(root.controller.snapshot.target.ownerPid)
                    === root.expectedPid,
                    "accepted production search inspected the wrong process")
                root.record("searchAccepted", true)
                var escape = root.findProperty(entry, "sequence", "Escape")
                root.require(escape, "production Escape shortcut is missing")
                root.stage = 3
                return
            }

            if (root.stage === 3) {
                var settings = root.findProperty(root.header, "tooltipText", "X-Ray settings")
                root.require(settings, "production settings button is missing")
                settings.clicked()
                root.stage = 4
                return
            }

            if (root.stage === 4) {
                if (root.controller.drawer !== "settings") return
                var savedRefresh = Number(root.controller.currentSettings.refreshSeconds)
                root.settingsDrawer.updateDraft("refreshSeconds", savedRefresh === 1 ? 2 : 1)
                var closeSettings = root.findProperty(root.settingsDrawer, "tooltipText", "Close drawer")
                    || root.descendants(root.settingsDrawer).find(function(item) {
                        return item && item.iconName === "close"
                    })
                root.require(closeSettings, "settings close button is missing")
                closeSettings.clicked()
                root.stage = 5
                return
            }

            if (root.stage === 5) {
                if (root.controller.drawer) return
                root.findProperty(root.header, "tooltipText", "X-Ray settings").clicked()
                root.stage = 6
                return
            }

            if (root.stage === 6) {
                if (root.controller.drawer !== "settings") return
                root.require(Number(root.settingsDrawer.draft.refreshSeconds)
                    === Number(root.controller.currentSettings.refreshSeconds),
                    "unsaved settings survived closing the production drawer")
                var defaultsButton = root.findProperty(root.settingsDrawer, "text", "Restore defaults")
                var applyButton = root.findProperty(root.settingsDrawer, "text", "Apply settings")
                root.require(defaultsButton && applyButton, "settings actions are missing")
                defaultsButton.clicked()
                applyButton.clicked()
                root.stage = 7
                return
            }

            if (root.stage === 7) {
                if (root.controller.busy || root.controller.drawer) return
                var spec = root.drilldowns[root.drilldownIndex]
                var card = root.named(spec.card)
                if (!card || !card.interactive)
                    console.log("XRAY_DRILLDOWN_STATE " + JSON.stringify({
                        "index": root.drilldownIndex,
                        "spec": spec,
                        "cardFound": !!card,
                        "cardInteractive": card ? card.interactive : null,
                        "cardDetailsCount": card ? card.detailsCount : null,
                        "busy": root.controller.busy,
                        "refreshInFlight": root.controller.refreshInFlight,
                        "snapshotKeys": Object.keys(root.controller.snapshot || {}),
                        "snapshotProcessPids": (
                            root.controller.snapshot.processes || []
                        ).map(function(row) { return Number(row.pid) }),
                        "snapshotExplanations":
                            root.controller.snapshot.explanations || []
                    }))
                root.require(card && card.interactive,
                    "production card is not drillable: " + spec.card)
                card.clicked()
                root.require(root.controller.drawer === "details",
                    spec.card + " click did not open its production drilldown")
                root.stage = 8
                return
            }

            if (root.stage === 8) {
                if (root.controller.drawer !== "details") return
                var spec = root.drilldowns[root.drilldownIndex]
                var card = root.named(spec.card)
                root.require(root.detailDrawer.domain === spec.domain,
                    spec.card + " opened the wrong production drilldown")
                root.require(root.detailDrawer.allRows.length === Number(card.detailsCount),
                    spec.card + " drilldown disagrees with its card count")
                if (spec.domain === "processes") {
                    var processDrawerHasChild = root.detailDrawer.allRows.some(
                        function(row) {
                            return Number(row.pid) === root.expectedChildPid
                        }
                    )
                    if (!processDrawerHasChild)
                        console.log("XRAY_PROCESS_DRAWER_STATE " + JSON.stringify({
                            "expectedChildPid": root.expectedChildPid,
                            "drawerPids": root.detailDrawer.allRows.map(
                                function(row) { return Number(row.pid) }
                            ),
                            "detailSnapshotPids": (
                                root.controller.detailSnapshot.processes || []
                            ).map(function(row) { return Number(row.pid) }),
                            "liveSnapshotPids": (
                                root.controller.snapshot.processes || []
                            ).map(function(row) { return Number(row.pid) }),
                            "target": root.controller.snapshot.target || {},
                            "coverage": root.controller.snapshot.coverage || {}
                        }))
                    root.require(processDrawerHasChild,
                        "process drilldown omits the independently known child")
                    var processTable = root.named("xrayProcessEvidenceTable")
                    root.require(processTable
                            && processTable.rows.length === root.detailDrawer.allRows.length,
                        "process evidence table does not expose the complete tree")
                    root.require(
                        processTable.theme.processEvidenceValueFontSize
                            >= processTable.theme.summaryFontSize
                            && processTable.theme.processEvidenceSecondaryFontSize
                                >= processTable.theme.labelFontSize
                            && processTable.theme.processEvidenceRowHeight
                                >= processTable.theme.processEvidenceValueFontSize * 2.5
                            && processTable.theme.processEvidenceRowHeight
                                <= processTable.theme.processEvidenceValueFontSize * 4,
                        "process evidence table escaped its readable compact density")
                    root.require(processTable.selectedCommand.indexOf("truth_fixture.py") >= 0,
                        "selected process command fell back to the executable path")
                    var commandStrip = root.named("xraySelectedProcessCommand")
                    var commandTextItem = root.named("xraySelectedProcessCommandText")
                    var commandPoint = commandTextItem.mapToItem(commandStrip, 0, 0)
                    root.require(commandPoint.y + commandTextItem.height
                            <= commandStrip.height + 1,
                        "selected process command is clipped by the table header")
                    var processText = root.textDump(processTable)
                    var processLabels = [
                        "PROCESS / COMMAND", "PID", "USER",
                        processTable.expanded ? "THREADS" : "THR",
                        "CPU", "MEMORY"
                    ]
                    if (processTable.expanded) processLabels.push("READ / WRITE")
                    processLabels
                        .forEach(function(label) {
                            root.require(processText.indexOf(label) >= 0,
                                "process evidence table is missing " + label)
                        })
                    root.detailDrawer.filterText = String(root.expectedPid)
                    root.require(processTable.rows.some(function(row) {
                        return Number(row.pid) === root.expectedPid
                    }), "process evidence filter hid its exact PID match")
                    root.detailDrawer.filterText = ""
                    processTable.chooseSort("cpu")
                    root.require(processTable.sortKey === "cpu" && processTable.descending,
                        "process evidence CPU sort did not start descending")
                    processTable.chooseSort("cpu")
                    root.require(!processTable.descending,
                        "process evidence CPU sort did not reverse")
                    processTable.chooseSort("tree")
                    var screenshotPath = Quickshell.env("XRAY_UI_SCREENSHOT")
                    if (screenshotPath && root.events.screenshotCaptured !== true) {
                        if (root.events.screenshotPending === true) return
                        root.record("screenshotPending", true)
                        root.detailDrawer.grabToImage(function(result) {
                            root.require(result && result.saveToFile(screenshotPath),
                                "process evidence screenshot could not be saved")
                            root.record("screenshotCaptured", true)
                        })
                        return
                    }
                }
                if (spec.domain === "connections") {
                    var hasListener = root.detailDrawer.allRows.some(function(row) {
                        return String(row.title).indexOf(String(root.expectedPort)) >= 0
                    })
                    if (!hasListener)
                        console.log("XRAY_CONNECTION_DRAWER_STATE " + JSON.stringify({
                            "expectedPort": root.expectedPort,
                            "detailRows": root.detailDrawer.allRows,
                            "detailConnections": root.controller.detailSnapshot.connections || [],
                            "liveConnections": root.controller.snapshot.connections || [],
                            "target": root.controller.snapshot.target || {}
                        }))
                    root.require(hasListener,
                        "connection drilldown omits the independently known listener")
                }
                if (spec.domain === "files") {
                    root.require(root.detailDrawer.allRows.some(function(row) {
                        return String(row.title).replace(/ \(deleted\)$/, "") === root.expectedPath
                    }), "file drilldown omits the independently known file")
                    var preparedPresentation = root.detailDrawer.preparedPresentation
                    var preparedSections = preparedPresentation.sections || []
                    if (preparedSections.length) {
                        var sectionId = String(preparedSections[0].id)
                        var visibleRowsBeforeToggle = root.detailDrawer.visibleRowCount
                        root.detailDrawer.toggleSection(sectionId)
                        root.require(
                            root.detailDrawer.preparedPresentation === preparedPresentation,
                            "file section toggle rebuilt its prepared evidence"
                        )
                        root.require(
                            root.detailDrawer.visibleRowCount
                                !== visibleRowsBeforeToggle,
                            "file section toggle did not change visible rows"
                        )
                        root.detailDrawer.toggleSection(sectionId)
                        root.require(
                            root.detailDrawer.preparedPresentation === preparedPresentation,
                            "file section restore rebuilt its prepared evidence"
                        )
                    }
                }
                root.require(root.descendants(root.detailDrawer).some(function(item) {
                    return item && item.contentHeight !== undefined
                        && item.height > 0 && item.clip === true
                        && item.contentHeight >= 0
                }), "detail drilldown has no bounded scrolling viewport")
                root.findProperty(root.detailDrawer, "tooltipText", "Close drawer").clicked()
                root.stage = 9
                return
            }

            if (root.stage === 9) {
                if (root.controller.drawer) return
                root.drilldownIndex += 1
                if (root.drilldownIndex < root.drilldowns.length) {
                    root.stage = 7
                    return
                }
                root.expectPanelStable = true
                root.named("xrayProcessCard").processSelected(root.expectedChildPid)
                root.stage = 90
                return
            }

            if (root.stage === 90) {
                root.require(!root.controller.capturingPreview,
                    "process-tree navigation hid X-Ray to recapture its preview")
                if (root.controller.busy) return
                root.require(root.panel.visible && root.unexpectedPanelHides === 0,
                    "process-tree navigation hid the inspection panel")
                root.expectPanelStable = false
                root.require(Number(root.controller.snapshot.target.ownerPid)
                    === root.expectedChildPid,
                    "process-tree navigation inspected the wrong child")
                var pause = root.findProperty(root.footer, "text", "Pause process")
                root.require(pause && pause.enabled,
                    "production pause action is unavailable for the controlled child")
                pause.clicked()
                root.stage = 901
                return
            }

            if (root.stage === 901) {
                if (root.controller.busy || root.controller.actionInFlight
                        || root.controller.refreshInFlight) return
                var resume = root.findProperty(root.footer, "text", "Resume process")
                if (!resume || !resume.enabled) return
                root.record("pauseAction", true)
                resume.clicked()
                root.stage = 902
                return
            }

            if (root.stage === 902) {
                if (root.controller.busy || root.controller.actionInFlight
                        || root.controller.refreshInFlight) return
                var pauseAgain = root.findProperty(root.footer, "text", "Pause process")
                if (!pauseAgain || !pauseAgain.enabled) return
                root.record("resumeAction", true)
                var terminate = root.findProperty(root.footer, "text", "Terminate process")
                root.require(terminate && terminate.enabled,
                    "production terminate action is unavailable for the controlled child")
                terminate.clicked()
                root.stage = 903
                return
            }

            if (root.stage === 903) {
                var pending = root.controller.pendingAction || {}
                if (pending.id !== "terminate") return
                var cancel = root.findProperty(entry, "text", "Cancel")
                root.require(cancel && cancel.visible,
                    "production terminate action did not open its confirmation")
                cancel.clicked()
                root.stage = 904
                return
            }

            if (root.stage === 904) {
                if (root.controller.pendingAction !== null) return
                root.record("confirmationCancel", true)
                root.expectPanelStable = true
                root.controller.inspect(root.query)
                root.stage = 91
                return
            }

            if (root.stage === 91) {
                root.require(!root.controller.capturingPreview,
                    "in-place target restore hid X-Ray to recapture its preview")
                if (root.controller.busy) return
                root.require(root.panel.visible && root.unexpectedPanelHides === 0,
                    "in-place target restore hid the inspection panel")
                root.expectPanelStable = false
                root.require(Number(root.controller.snapshot.target.ownerPid)
                    === root.expectedPid,
                    "in-place target restore inspected the wrong root")
                root.findProperty(
                    root.header, "tooltipText", "Saved reports"
                ).clicked()
                root.stage = 10
                return
            }

            if (root.stage === 10) {
                if (root.controller.drawer !== "capsule") return
                var exportButton = root.findProperty(
                    root.capsuleDrawer, "text", "Export private report"
                )
                root.require(exportButton && exportButton.enabled,
                    "live capsule export is unavailable")
                exportButton.clicked()
                root.stage = 11
                return
            }

            if (root.stage === 11) {
                if (root.capsuleDrawer.status.indexOf("Exported and copied path:") < 0)
                    return
                var lines = root.capsuleDrawer.status.split("\n")
                root.capsulePath = lines[lines.length - 1]
                root.require(root.capsulePath.endsWith(".xray.zip"),
                    "capsule export returned the wrong path")
                root.capsuleDrawer.capsulePath = root.capsulePath
                root.findProperty(root.capsuleDrawer, "text", "Open report").clicked()
                root.stage = 12
                return
            }

            if (root.stage === 12) {
                if (root.controller.busy || !root.controller.offline) return
                root.require((root.controller.snapshot.actions || []).length === 0,
                    "offline production UI retained live actions")
                root.findProperty(
                    root.header, "tooltipText", "Saved reports"
                ).clicked()
                root.stage = 13
                return
            }

            if (root.stage === 13) {
                if (root.controller.drawer !== "capsule") return
                var exportOffline = root.findProperty(
                    root.capsuleDrawer, "text", "Export private report"
                )
                var compareOffline = root.findProperty(
                    root.capsuleDrawer, "text", "Compare with current"
                )
                root.require(!exportOffline.enabled && !compareOffline.enabled,
                    "offline production drawer still permits live mutations")
                root.record("publicEntry", true)
                root.record("cardTruth", true)
                root.record("drilldown", true)
                root.record("settings", true)
                root.record("offline", true)
                root.require(root.events.searchAccepted === true,
                    "production search was never accepted")
                root.require(root.events.pauseAction === true
                    && root.events.resumeAction === true,
                    "production process controls did not complete their controlled round trip")
                root.require(root.events.confirmationCancel === true,
                    "production destructive confirmation was not exercised")
                root.finish()
            }
        }
    }
}
