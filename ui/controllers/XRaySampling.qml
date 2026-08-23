import QtQuick
import "../DetailDomains.js" as DetailDomains

Item {
    id: root

    required property var bridge
    required property bool opened
    required property var capabilities
    required property int inspectionGeneration
    required property var pendingAction
    required property string drawer
    required property string detailsDrawer
    required property string detailDomain
    property bool busy: false
    property bool refreshInFlight: false
    property bool capturingPreview: false
    property bool offline: false
    property var snapshot: ({})
    property var defaultSettings: ({})
    property var currentSettings: ({})
    property var performanceSamples: []
    property var previousMetrics: ({})
    property var pendingPreview: null
    readonly property int performanceWindowSeconds: 60
    readonly property int refreshIntervalMs: Number(
        currentSettings.refreshSeconds || defaultSettings.refreshSeconds || 2
    ) * 1000
    signal noticeRequested(string message)
    signal detailPatchRequested(var patch)

    function isCurrentInspection(generation) {
        return opened && generation === inspectionGeneration;
    }

    function beginInspection() {
        refreshTimer.stop();
        previewTimer.stop();
        pendingPreview = null;
    }

    function refresh() {
        var target = snapshot.target || {};
        if (offline || busy || refreshInFlight || pendingAction
                || !snapshot.target || !isRefreshableTarget(target)) return;
        var generation = inspectionGeneration;
        refreshInFlight = true;
        bridge.send("refresh", {"compact": true}, function(data, error) {
            if (!isCurrentInspection(generation)) return;
            refreshInFlight = false;
            if (error) {
                noticeRequested(error);
                resumeIfEligible();
                return;
            }
            if (data && data.snapshotPatch) {
                detailPatchRequested(data.snapshotPatch);
                data = Object.assign({}, snapshot, data.snapshotPatch);
            }
            finishSnapshot(data, false, generation, false);
        });
    }

    function finishSnapshot(data, resetSamples, generation, allowPreview) {
        if (!isCurrentInspection(generation)) return;
        if (!data) {
            busy = false;
            capturingPreview = false;
            return;
        }
        var context = data.context || {};
        var window = context.window || {};
        var needsPreview = allowPreview === true
            && currentSettings.capturePreview !== false
            && capabilities.windowPreview === true
            && !!window.address
            && context.previewEligible === true
            && !context.previewPath;
        if (needsPreview) {
            previewTimer.interval = capturingPreview ? 0 : 100;
            pendingPreview = {
                "snapshot": data,
                "resetSamples": resetSamples,
                "generation": generation
            };
            capturingPreview = true;
            previewTimer.restart();
            return;
        }
        if (allowPreview !== true && currentSettings.capturePreview !== false
                && !context.previewPath && context.previewEligible === true) {
            context = Object.assign({}, context);
            context.previewStatus = "deferred";
            context.previewError = "";
            data.context = context;
        }
        busy = false;
        capturingPreview = false;
        applySnapshot(data, resetSamples);
    }

    function applySnapshot(data, resetSamples) {
        offline = false;
        previousMetrics = resetSamples ? ({}) : (snapshot.metrics || {});
        snapshot = data || {};
        var metrics = snapshot.metrics || {};
        currentSettings = snapshot.settings || currentSettings;
        var capturedAt = Date.now();
        var cutoff = capturedAt - performanceWindowSeconds * 1000;
        var retained = (resetSamples ? [] : performanceSamples).filter(function(sample) {
            return Number(sample.capturedAt || 0) >= cutoff;
        });
        performanceSamples = retained.concat([{
            "capturedAt": capturedAt,
            "cpuPercent": metrics.cpuAvailable === false
                ? null
                : Number(metrics.cpuPercent || 0),
            "memoryBytes": Number(metrics.memoryBytes || 0)
        }]).slice(-performanceWindowSeconds - 1);
        resumeIfEligible();
    }

    function isRefreshableTarget(target) {
        var kind = String((target || {}).kind || "");
        return !!(target || {}).rootPid || kind === "service" || kind === "container";
    }

    function resumeIfEligible() {
        var target = snapshot.target || {};
        if (opened && !offline && !busy && !pendingAction
                && snapshot.samplingPaused !== true
                && isRefreshableTarget(target))
            refreshTimer.restart();
    }

    function stop() { refreshTimer.stop(); }
    function restart() { refreshTimer.restart(); }

    Timer {
        id: refreshTimer
        interval: root.refreshIntervalMs
        repeat: false
        onTriggered: root.refresh()
    }

    Timer {
        id: previewTimer
        interval: 100
        repeat: false
        onTriggered: {
            var pending = root.pendingPreview;
            root.pendingPreview = null;
            if (!pending || !root.isCurrentInspection(Number(pending.generation))) {
                root.capturingPreview = false;
                return;
            }
            bridge.send("capturePreview", {}, function(data, error) {
                var captured = pending.snapshot;
                var resetSamples = pending.resetSamples;
                var generation = Number(pending.generation);
                if (!root.isCurrentInspection(generation)) return;
                if (error) root.noticeRequested(error);
                if (captured && data) {
                    var context = Object.assign({}, captured.context || {});
                    context.previewPath = data.previewPath || "";
                    context.previewStatus = data.previewStatus
                        || (data.previewPath ? "ready" : "failed");
                    context.previewError = data.previewError || "";
                    captured.context = context;
                }
                root.busy = false;
                root.capturingPreview = false;
                if (captured) root.applySnapshot(captured, resetSamples);
            });
        }
    }
}
