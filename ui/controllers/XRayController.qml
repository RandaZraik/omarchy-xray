import QtQuick
import ".."
import "../DetailDomains.js" as DetailDomains

Item {
    id: root
    objectName: "xrayController"

    property bool opened: false
    property alias busy: sampling.busy
    property alias refreshInFlight: sampling.refreshInFlight
    property alias capturingPreview: sampling.capturingPreview
    property bool pickingWindow: false
    property alias snapshot: sampling.snapshot
    property var catalog: ({})
    property var capabilities: ({})
    property var settingsSpec: []
    property alias defaultSettings: sampling.defaultSettings
    property alias currentSettings: sampling.currentSettings
    property string notice: ""
    property string drawer: ""
    readonly property string detailsDrawer: "details"
    readonly property string settingsDrawer: "settings"
    readonly property string capsuleDrawer: "capsule"
    property string detailDomain: ""
    property var detailSnapshot: ({})
    property alias performanceSamples: sampling.performanceSamples
    property alias previousMetrics: sampling.previousMetrics
    property alias actionInFlight: actions.actionInFlight
    property alias yieldingFocus: actions.yieldingFocus
    property alias pendingAction: actions.pendingAction
    property alias offline: sampling.offline
    property bool catalogRequested: false
    property double catalogLoadedAt: 0
    property int inspectionGeneration: 0
    readonly property int refreshIntervalMs: sampling.refreshIntervalMs
    readonly property int performanceWindowSeconds: sampling.performanceWindowSeconds
    readonly property bool interactionBlocked: busy || capturingPreview
        || pickingWindow || yieldingFocus || actionInFlight
        || pendingAction !== null || drawer !== ""

    signal closed()
    signal querySynchronized(string query)
    signal clipboardRequested(string text)
    signal capsuleStatusChanged(string message)

    function beginInspection() {
        inspectionGeneration += 1;
        sampling.beginInspection();
        refreshInFlight = false;
        capturingPreview = false;
        pickingWindow = false;
        actions.reset();
        return inspectionGeneration;
    }

    function isCurrentInspection(generation) {
        return opened && generation === inspectionGeneration;
    }

    function open(payloadJson) {
        var generation = beginInspection();
        root.querySynchronized("");
        opened = true;
        busy = true;
        capturingPreview = currentSettings.capturePreview !== false;
        drawer = "";
        detailSnapshot = ({});
        notice = "";
        bridge.send("bootstrap", {}, function(data, error) {
            if (!isCurrentInspection(generation)) return;
            if (error) {
                busy = false;
                capturingPreview = false;
                showNotice(error);
                return;
            }
            busy = false;
            if (!data) {
                capturingPreview = false;
                return;
            }
            capabilities = data.capabilities || {};
            settingsSpec = data.settingsSpec || [];
            defaultSettings = data.settingsDefaults || {};
            currentSettings = data.settings || {};
            if (currentSettings.capturePreview === false) {
                capturingPreview = false;
            }
            var payload = {};
            try { payload = JSON.parse(payloadJson || "{}"); } catch (ignored) {}
            if (payload.query) {
                inspect(payload.query, true);
                return;
            }
            bridge.send("inspectFocused", {}, function(snapshotData, error) {
                if (!isCurrentInspection(generation)) return;
                if (error) {
                    busy = false;
                    capturingPreview = false;
                    showNotice(error);
                    return;
                }
                if (snapshotData && snapshotData.target)
                    finishSnapshot(snapshotData, true, generation, true);
                else {
                    busy = false;
                    capturingPreview = false;
                    requestCatalog(true);
                }
            });
        });
    }

    function close() {
        beginInspection();
        opened = false;
        drawer = "";
        detailSnapshot = ({});
        snapshot = ({});
        performanceSamples = [];
        previousMetrics = ({});
        offline = false;
        busy = false;
        notice = "";
        if (bridge.running)
            bridge.send("closeInspection", {}, function() {});
        root.closed();
    }

    function requestCatalog(force) {
        if (catalogRequested) return;
        var fresh = Object.keys(catalog || {}).length > 0
            && Date.now() - catalogLoadedAt < 30000;
        if (fresh && force !== true) return;
        catalogRequested = true;
        catalogBridge.send("catalog", {}, function(data, error) {
            catalogRequested = false;
            catalogBridge.stop();
            if (error) {
                showNotice(error);
                return;
            }
            if (data) {
                catalog = data;
                catalogLoadedAt = Date.now();
            }
        });
    }

    function inspect(query, captureInitialPreview) {
        var value = String(query || "").trim();
        if (!value) return;
        var generation = beginInspection();
        busy = true;
        root.querySynchronized(value);
        bridge.send("inspect", {"query": value}, function(data, error) {
            if (isCurrentInspection(generation) && error)
                showNotice(error);
            finishSnapshot(data, true, generation, captureInitialPreview === true);
        });
    }

    function finishSnapshot(data, resetSamples, generation, allowPreview) {
        sampling.finishSnapshot(data, resetSamples, generation, allowPreview);
    }

    function applySnapshot(data, resetSamples) {
        sampling.applySnapshot(data, resetSamples);
    }

    function applyOfflineSnapshot(data, sourcePath) {
        sampling.stop();
        var archived = data || {};
        var target = Object.assign({}, archived.target || {});
        target.label = String(target.label || "Inspection") + " · OFFLINE";
        archived.target = target;
        archived.actions = [];
        archived.samplingPaused = true;
        snapshot = archived;
        offline = true;
        performanceSamples = [{
            "capturedAt": Date.now(),
            "cpuPercent": (archived.metrics || {}).cpuAvailable === false
                ? null
                : Number((archived.metrics || {}).cpuPercent || 0),
            "memoryBytes": Number((archived.metrics || {}).memoryBytes || 0)
        }];
        previousMetrics = ({});
        drawer = "";
        capturingPreview = false;
        showNotice("Opened saved report · " + sourcePath);
    }

    function refresh() { sampling.refresh(); }

    function focusProcess(pid) {
        if (offline) {
            showNotice("Offline reports are read-only");
            return;
        }
        var generation = beginInspection();
        root.querySynchronized("pid:" + pid);
        busy = true;
        bridge.send("focusProcess", {"pid": pid}, function(data, error) {
            if (isCurrentInspection(generation) && error)
                showNotice(error);
            finishSnapshot(data, true, generation, false);
        });
    }

    function showDetails(domain) {
        detailDomain = domain;
        detailSnapshot = snapshot;
        drawer = detailsDrawer;
    }

    function toggleDrawer(name) {
        drawer = drawer === name ? "" : name;
    }

    function closeDrawer() { drawer = ""; }

    function dismissDrawerAfterPointer() {
        Qt.callLater(closeDrawer);
    }

    function selectProcessAfterPointer(pid) {
        Qt.callLater(function() {
            drawer = "";
            focusProcess(pid);
        });
    }

    function cancelActionAfterPointer() {
        actions.cancelAfterPointer();
    }

    function confirmActionAfterPointer(actionId, expectedInspectionId) {
        actions.confirmAfterPointer(actionId, expectedInspectionId);
    }

    function showNotice(message) {
        notice = message;
        noticeTimer.restart();
    }

    function pickWindow() {
        if (!capabilities.windowPicker) {
            showNotice("Window picking is unavailable because slurp is not installed");
            return;
        }
        var generation = beginInspection();
        pickingWindow = true;
        bridge.send("pickWindow", {}, function(data, error) {
            if (generation !== inspectionGeneration) return;
            pickingWindow = false;
            if (error) {
                showNotice(error);
                resumeRefreshIfEligible();
                return;
            }
            if (data && !data.cancelled) {
                var query = String((data.target || {}).query || "");
                if (query) root.querySynchronized(query);
                finishSnapshot(data, true, generation, true);
            }
            else {
                capturingPreview = false;
                resumeRefreshIfEligible();
            }
        });
    }

    function resumeRefreshIfEligible() { sampling.resumeIfEligible(); }

    function requestAction(action) {
        actions.request(action);
    }

    function toggleSampling() {
        actions.toggleSampling();
    }

    function configure(values) {
        var generation = inspectionGeneration;
        bridge.send("configure", {"settings": values}, function(data, error) {
            if (!isCurrentInspection(generation)) return;
            if (error) {
                showNotice(error);
                return;
            }
            if (!data) return;
            currentSettings = data;
            showNotice("Settings applied");
            drawer = "";
            if (!offline) refresh();
        });
    }

    function resetBaseline() {
        actions.resetBaseline();
    }

    function exportCapsule() {
        capsules.exportCapsule();
    }

    function copyReport() {
        capsules.copyReport();
    }

    function openCapsule(path) {
        capsules.openCapsule(path);
    }

    function compareCapsule(path) {
        capsules.compareCapsule(path);
    }

    function stopRefresh() { sampling.stop(); }
    function restartRefresh() { sampling.restart(); }

    BackendBridge {
        id: bridge
        onFailed: function(message) {
            root.busy = false;
            root.refreshInFlight = false;
            actions.actionInFlight = false;
            root.capturingPreview = false;
            actions.yieldingFocus = false;
            root.catalogRequested = false;
            root.showNotice(message);
            root.resumeRefreshIfEligible();
        }
    }

    BackendBridge {
        id: catalogBridge
        onFailed: function(message) {
            root.catalogRequested = false;
            root.showNotice(message);
            catalogBridge.stop();
        }
    }

    XRayActions {
        id: actions
        host: root
        bridge: bridge
    }

    XRayCapsules {
        id: capsules
        host: root
        bridge: bridge
    }

    XRaySampling {
        id: sampling
        bridge: bridge
        opened: root.opened
        capabilities: root.capabilities
        inspectionGeneration: root.inspectionGeneration
        pendingAction: root.pendingAction
        drawer: root.drawer
        detailsDrawer: root.detailsDrawer
        detailDomain: root.detailDomain
        onNoticeRequested: function(message) { root.showNotice(message); }
        onDetailPatchRequested: function(patch) {
            if (root.drawer === root.detailsDrawer
                    && DetailDomains.patchTouches(root.detailDomain, patch))
                root.detailSnapshot = Object.assign({}, root.detailSnapshot, patch);
        }
    }

    Timer {
        id: noticeTimer
        interval: 2600
        onTriggered: root.notice = ""
    }

    Component.onDestruction: {
        bridge.stop();
        catalogBridge.stop();
    }
}
