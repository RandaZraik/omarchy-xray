import QtQuick
import Quickshell
import "ui"

ShellRoot {
    id: root

    property bool completed: false
    property int stage: 0

    BackendBridge {
        id: bridge
        requestTimeoutMs: 10
        windowPickTimeoutMs: 500
    }

    Component.onCompleted: {
        bridge.send("pickWindow", {}, function(data, error) {
            if (completed) return;
            if (error || !data || data.picked !== true) {
                console.log("XRAY_BACKEND_TIMEOUT_ERROR " + error);
                Qt.quit();
                return;
            }
            stage = 1;
            bridge.send("bootstrap", {}, function(data, error) {
                if (completed) return;
                if (data || error.indexOf("timed out") < 0) {
                    console.log("XRAY_BACKEND_TIMEOUT_ERROR " + error);
                    Qt.quit();
                    return;
                }
                stage = 2;
                bridge.send("bootstrap", {}, function(recovered, recoveryError) {
                    completed = true;
                    if (recoveryError || !recovered || recovered.ready !== true) {
                        console.log("XRAY_BACKEND_TIMEOUT_ERROR recovery " + recoveryError);
                        Qt.quit();
                        return;
                    }
                    console.log("XRAY_BACKEND_TIMEOUT ok");
                    Qt.quit();
                });
            });
        });
    }

    Timer {
        interval: 4000
        running: true
        onTriggered: {
            if (!root.completed)
                console.log("XRAY_BACKEND_TIMEOUT_ERROR callback was never resolved");
            Qt.quit();
        }
    }
}
