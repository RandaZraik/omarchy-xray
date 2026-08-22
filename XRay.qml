import QtQuick
import Quickshell
import "ui"

Item {
    id: root
    objectName: "xrayEntry"

    property var shell: null
    property var manifest: null
    property alias opened: overlay.opened

    function open(payloadJson) {
        overlay.open(payloadJson || "{}");
    }

    function close() {
        overlay.close();
    }

    function toggle(payloadJson) {
        opened ? close() : open(payloadJson || "{}");
    }

    XRayOverlay {
        id: overlay

    }
}
