import QtQuick

Item {
    id: root

    required property var host
    required property var bridge
    property bool actionInFlight: false
    property bool yieldingFocus: false
    property var pendingAction: null
    property var pendingFocusAction: null

    function reset() {
        focusActionTimer.stop();
        actionInFlight = false;
        yieldingFocus = false;
        pendingAction = null;
        pendingFocusAction = null;
    }

    function request(action) {
        if (host.offline || host.interactionBlocked || !action || !action.available) return;
        if (action.confirm) {
            var inspectionId = Number((host.snapshot.target || {}).inspectionId || 0);
            if (!inspectionId) return;
            host.stopRefresh();
            pendingAction = Object.assign({}, action, {
                "expectedInspectionId": inspectionId
            });
            return;
        }
        run(action.id, Number((host.snapshot.target || {}).inspectionId || 0));
    }

    function cancelAfterPointer() {
        Qt.callLater(function() {
            pendingAction = null;
            host.resumeRefreshIfEligible();
        });
    }

    function confirmAfterPointer(actionId, expectedInspectionId) {
        Qt.callLater(function() { run(actionId, expectedInspectionId); });
    }

    function run(actionId, expectedInspectionId) {
        pendingAction = null;
        var currentInspectionId = Number((host.snapshot.target || {}).inspectionId || 0);
        if (!expectedInspectionId || expectedInspectionId !== currentInspectionId) {
            host.showNotice("The inspected target changed; review it before using this action");
            host.resumeRefreshIfEligible();
            return;
        }
        if (actionId === "focus") {
            yieldingFocus = true;
            pendingFocusAction = {
                "actionId": actionId,
                "expectedInspectionId": expectedInspectionId,
                "generation": host.inspectionGeneration
            };
            focusActionTimer.restart();
            return;
        }
        dispatch(actionId, expectedInspectionId);
    }

    function dispatch(actionId, expectedInspectionId) {
        var generation = host.inspectionGeneration;
        var inspectionId = Number((host.snapshot.target || {}).inspectionId || 0);
        if (!inspectionId || inspectionId !== expectedInspectionId || actionInFlight) {
            yieldingFocus = false;
            pendingFocusAction = null;
            host.showNotice("The inspected target changed; review it before using this action");
            host.resumeRefreshIfEligible();
            return;
        }
        actionInFlight = true;
        bridge.send("action", {
            "action": actionId,
            "inspectionId": inspectionId
        }, function(data, error) {
            if (!host.isCurrentInspection(generation)) return;
            actionInFlight = false;
            if (error) {
                yieldingFocus = false;
                pendingFocusAction = null;
                host.showNotice(error);
                host.resumeRefreshIfEligible();
                return;
            }
            if (actionId === "focus") {
                yieldingFocus = false;
                pendingFocusAction = null;
                if (data && data.ok) host.close();
                else if (data) host.showNotice(data.message || "Could not focus the window");
                return;
            }
            if (data) host.showNotice(data.message || "Action complete");
            if (data && data.ok) host.refresh();
        });
    }

    function toggleSampling() {
        if (host.offline || host.interactionBlocked) return;
        var generation = host.inspectionGeneration;
        var paused = !(host.snapshot.samplingPaused === true);
        bridge.send("setSamplingPaused", {"paused": paused}, function(data, error) {
            if (!host.isCurrentInspection(generation)) return;
            if (error) {
                host.showNotice(error);
                host.resumeRefreshIfEligible();
                return;
            }
            if (!data) return;
            var next = Object.assign({}, host.snapshot);
            next.samplingPaused = data.samplingPaused;
            host.snapshot = next;
            if (data.samplingPaused) host.stopRefresh();
            else host.restartRefresh();
        });
    }

    function resetBaseline() {
        if (host.offline) return;
        var generation = host.inspectionGeneration;
        bridge.send("resetBaseline", {}, function(data, error) {
            if (!host.isCurrentInspection(generation)) return;
            if (error) {
                host.showNotice(error);
                return;
            }
            if (data)
                host.applySnapshot(data, false);
        });
    }

    Timer {
        id: focusActionTimer
        interval: 100
        repeat: false
        onTriggered: {
            var pending = root.pendingFocusAction;
            root.pendingFocusAction = null;
            if (!pending || pending.generation !== root.host.inspectionGeneration) {
                root.yieldingFocus = false;
                root.host.resumeRefreshIfEligible();
                return;
            }
            root.dispatch(pending.actionId, pending.expectedInspectionId);
        }
    }
}
