import QtQuick
import Quickshell.Io

QtObject {
    id: root

    readonly property string backendPath: decodeURIComponent(Qt.resolvedUrl("../backend/main.py").toString().replace(/^file:\/\//, ""))
    property int serial: 0
    property var pending: ({})
    property var queued: []
    property bool stopping: false
    property bool recovering: false
    property int requestTimeoutMs: 20000
    property int windowPickTimeoutMs: 65000
    property int managedActionTimeoutMs: 35000
    readonly property bool running: backend.running
    signal failed(string message)

    function start() {
        if (!backend.running && !recovering)
            backend.running = true;
    }

    function stop() {
        if (!backend.running) {
            stopping = false;
            return;
        }
        stopping = true;
        send("shutdown", {}, function() {});
    }

    function send(command, fields, callback) {
        serial += 1;
        var id = String(serial);
        var request = { "id": id, "command": command };
        for (var key in fields || {})
            request[key] = fields[key];
        pending[id] = {
            "callback": callback || function() {},
            "deadline": Date.now() + timeoutFor(command, fields)
        };
        if (!requestWatchdog.running) requestWatchdog.start();
        var line = JSON.stringify(request) + "\n";
        if (!backend.running || recovering || (stopping && command !== "shutdown")) {
            queued.push(line);
            if (!stopping && !recovering) start();
        } else {
            backend.write(line);
        }
        return id;
    }

    function timeoutFor(command, fields) {
        if (command === "pickWindow")
            return Math.max(requestTimeoutMs, windowPickTimeoutMs);
        if (command === "action" && String((fields || {}).action || "") === "relaunch")
            return Math.max(requestTimeoutMs, managedActionTimeoutMs);
        return requestTimeoutMs;
    }

    function flush() {
        while (queued.length > 0)
            backend.write(queued.shift());
    }

    function handleLine(line) {
        var reply;
        try {
            reply = JSON.parse(line);
        } catch (error) {
            recoverBackend("The X-Ray backend returned invalid data");
            return;
        }
        if (!reply || typeof reply !== "object" || !String(reply.id || "")) {
            recoverBackend("The X-Ray backend returned invalid data");
            return;
        }
        if (!pending[reply.id]) return;
        if (!reply.ok) {
            completeRequest(reply.id, null, String(reply.error || "Request failed"));
            return;
        }
        completeRequest(reply.id, reply.data, "");
    }

    function completeRequest(id, data, error) {
        var request = pending[id];
        if (!request) return false;
        delete pending[id];
        if (Object.keys(pending).length === 0) requestWatchdog.stop();
        request.callback(data, error);
        return true;
    }

    function failPending(message) {
        var requests = pending;
        pending = ({});
        requestWatchdog.stop();
        Object.keys(requests).forEach(function(id) {
            var callback = requests[id] ? requests[id].callback : null;
            if (callback) callback(null, message);
        });
    }

    function recoverBackend(message) {
        if (recovering) return;
        recovering = true;
        stopping = false;
        queued = [];
        failPending(message);
        if (backend.running)
            backend.running = false;
        else
            finishRecovery();
    }

    function finishRecovery() {
        recovering = false;
        if (queued.length > 0) start();
    }

    property Process backend: Process {
        command: ["python3", root.backendPath]
        stdinEnabled: true
        stdout: SplitParser {
            onRead: function(line) { root.handleLine(line); }
        }
        stderr: SplitParser {
            onRead: function(line) {
                if (String(line || "").trim())
                    console.warn("xray:", line);
            }
        }
        onStarted: root.flush()
        onExited: function(exitCode) {
            if (root.recovering) {
                root.finishRecovery();
                return;
            }
            var shouldRestart = exitCode === 0 && root.queued.length > 0;
            root.stopping = false;
            if (shouldRestart) {
                root.start();
            } else {
                var message = exitCode === 0
                    ? "The X-Ray backend stopped before completing the request"
                    : "The X-Ray backend stopped unexpectedly";
                if (Object.keys(root.pending).length > 0)
                    root.failPending(message);
                else if (exitCode !== 0)
                    root.failed(message);
                root.queued = [];
            }
        }
    }


    property Timer requestWatchdog: Timer {
        interval: 250
        repeat: true
        running: false
        onTriggered: {
            var now = Date.now();
            Object.keys(root.pending).forEach(function(id) {
                var request = root.pending[id];
                if (!request || Number(request.deadline) > now) return;
                root.recoverBackend("The X-Ray backend timed out handling the request");
            });
        }
    }
}
