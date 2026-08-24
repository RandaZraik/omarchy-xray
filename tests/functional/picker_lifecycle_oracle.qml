import QtQuick
import Quickshell
import "ui/controllers" as Controllers

ShellRoot {
    id: root

    property int stage: 0
    property double deadline: Date.now() + 3000
    property string synchronizedQuery: ""
    property string expectedQuery: Quickshell.env("XRAY_PICKER_EXPECTED_QUERY")

    Controllers.XRayController {
        id: controller
        onQuerySynchronized: function(query) {
            if (query) root.synchronizedQuery = query
        }
    }

    Component.onCompleted: controller.open("{}")

    Timer {
        interval: 10
        repeat: true
        running: true
        onTriggered: {
            if (Date.now() > root.deadline) {
                console.log("XRAY_PICKER_ERROR timed out at stage " + root.stage)
                Qt.quit()
                return
            }
            if (root.stage === 0) {
                if (controller.busy || controller.catalogRequested) return
                if (!controller.opened) {
                    console.log("XRAY_PICKER_ERROR controller closed during startup")
                    Qt.quit()
                    return
                }
                controller.pickWindow()
                if (!controller.opened || !controller.pickingWindow) {
                    console.log("XRAY_PICKER_ERROR picker closed the inspection lifecycle")
                    Qt.quit()
                    return
                }
                root.stage = 1
                return
            }
            if (controller.pickingWindow) return
            if (!controller.opened) {
                console.log("XRAY_PICKER_ERROR cancelled picker closed the inspection")
                Qt.quit()
                return
            }
            if (root.expectedQuery
                    && root.synchronizedQuery !== root.expectedQuery) {
                console.log("XRAY_PICKER_ERROR picked target query was not synchronized")
                Qt.quit()
                return
            }
            console.log("XRAY_PICKER ok")
            running = false
            controller.close()
            Qt.quit()
        }
    }
}
