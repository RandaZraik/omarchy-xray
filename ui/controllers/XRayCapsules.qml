import QtQuick

Item {
    id: root

    required property var host
    required property var bridge

    function exportCapsule() {
        if (host.offline) {
            host.capsuleStatusChanged("Offline reports cannot be exported again.");
            return;
        }
        var generation = host.inspectionGeneration;
        bridge.send("exportCapsule", {}, function(data, error) {
            if (!host.isCurrentInspection(generation)) return;
            if (error) {
                host.capsuleStatusChanged(error);
                return;
            }
            if (!data) return;
            host.clipboardRequested(data.path);
            host.capsuleStatusChanged("Exported and copied path:\n" + data.path);
        });
    }

    function copyReport() {
        if (host.offline) {
            host.capsuleStatusChanged("Offline reports do not have live data.");
            return;
        }
        var generation = host.inspectionGeneration;
        bridge.send("report", {}, function(data, error) {
            if (!host.isCurrentInspection(generation)) return;
            if (error) {
                host.capsuleStatusChanged(error);
                return;
            }
            if (!data) return;
            host.clipboardRequested(data.text);
            host.capsuleStatusChanged("Redacted report copied to the clipboard.");
        });
    }

    function openCapsule(path) {
        var generation = host.beginInspection();
        host.busy = true;
        bridge.send("openCapsule", {"path": path}, function(data, error) {
            if (!host.isCurrentInspection(generation)) return;
            host.busy = false;
            if (error) {
                host.showNotice(error);
                host.resumeRefreshIfEligible();
                return;
            }
            if (data && data.snapshot) {
                host.querySynchronized("");
                host.applyOfflineSnapshot(data.snapshot, path);
            } else host.resumeRefreshIfEligible();
        });
    }

    function compareCapsule(path) {
        if (host.offline) {
            host.capsuleStatusChanged("Choose a live target before comparing reports.");
            return;
        }
        var generation = host.inspectionGeneration;
        bridge.send("compareCapsule", {"path": path}, function(data, error) {
            if (!host.isCurrentInspection(generation)) return;
            if (error) {
                host.capsuleStatusChanged(error);
                return;
            }
            if (!data || !data.domains) return;
            var domains = data.domains;
            host.capsuleStatusChanged(
                "Compared: processes +" + domains.processes.added + "/−" + domains.processes.removed
                + ", sockets +" + domains.connections.added + "/−" + domains.connections.removed
                + ", files +" + domains.files.added + "/−" + domains.files.removed
                + ", devices +" + domains.devices.added + "/−" + domains.devices.removed
                + ", runtime +" + domains.runtime.added + "/−" + domains.runtime.removed
                + ". CPU " + String((data.metrics || {}).cpuPercent ?? "—")
                + ", memory " + String((data.metrics || {}).memoryBytes ?? "—")
                + ", GPU " + String((data.metrics || {}).gpuPercent ?? "—") + "."
            );
        });
    }
}
