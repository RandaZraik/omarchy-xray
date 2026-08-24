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

    function browse() {
        overlay.browse();
    }

    function details(domain) {
        overlay.showDetails(String(domain || ""));
    }

    XRayOverlay {
        id: overlay
        appLibrary: root.shell ? root.shell.appLibrary : null
    }
}
