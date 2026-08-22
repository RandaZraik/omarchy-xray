import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import qs.Commons as Commons
import qs.Ui
import "controllers"
import "drawers"
import "views"
import "DetailDomains.js" as DetailDomains

Item {
    id: root
    objectName: "xrayOverlay"

    property alias opened: controller.opened
    property var inspectionScreen: null

    function open(payloadJson) {
        inspectionScreen = focusedScreen();
        controller.open(payloadJson);
    }
    function close() { controller.close(); }

    function focusedScreen() {
        var monitor = Hyprland.focusedMonitor;
        if (!monitor) return null;
        for (var index = 0; index < Quickshell.screens.length; index++) {
            var candidate = Quickshell.screens[index];
            if (candidate.name === monitor.name) return candidate;
        }
        return null;
    }

    XRayController {
        id: controller
        objectName: "xrayController"
        onClosed: root.inspectionScreen = null
        onPaletteDismissRequested: appHeader.paletteVisible = false
        onQuerySynchronized: function(query) { appHeader.queryText = query; }
        onClipboardRequested: function(text) { Quickshell.clipboardText = text; }
        onCapsuleStatusChanged: function(message) { capsuleDrawer.status = message; }
    }

    XRayTheme { id: theme }
    XRayContract { id: contract }

    Shortcut {
        sequence: "Escape"
        context: Qt.ApplicationShortcut
        enabled: controller.opened
        onActivated: controller.dismissTopLayer(appHeader.paletteVisible)
    }

    Shortcut {
        sequence: "Ctrl+K"
        context: Qt.ApplicationShortcut
        enabled: controller.opened && controller.drawer === "" && !controller.pendingAction
        onActivated: appHeader.focusSearch(true)
    }

    Shortcut {
        sequence: "Ctrl+R"
        context: Qt.ApplicationShortcut
        enabled: controller.opened && !controller.offline && controller.drawer === "" && !controller.pendingAction && !controller.refreshInFlight
        onActivated: controller.refresh()
    }

    PanelWindow {
        id: panel
        objectName: "xrayPanel"
        visible: controller.opened && !controller.capturingPreview
            && !controller.pickingWindow && !controller.yieldingFocus
        screen: root.inspectionScreen || root.focusedScreen()
        anchors { top: true; bottom: true; left: true; right: true }
        color: theme.transparent
        WlrLayershell.namespace: contract.layerNamespace
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
        exclusionMode: ExclusionMode.Ignore

        Rectangle { anchors.fill: parent; color: theme.scrim }
        MouseArea { anchors.fill: parent; onClicked: controller.close() }

        BorderSurface {
            id: desk
            objectName: "xrayDesk"
            width: Math.min(theme.panelMaxWidth, panel.width - theme.outerGap * 2)
            height: Math.min(theme.panelMaxHeight, panel.height - theme.outerGap * 2)
            anchors.centerIn: parent
            radius: theme.radius
            color: theme.panel
            borderSpec: Commons.Border.flat(theme.strongAccentBorder, theme.borderWidth)
            padding: theme.panelPadding

            MouseArea { anchors.fill: parent; onClicked: {} }

            FocusScope {
                anchors.fill: parent
                anchors.topMargin: desk.contentTopInset
                anchors.rightMargin: desk.contentRightInset
                anchors.bottomMargin: desk.contentBottomInset
                anchors.leftMargin: desk.contentLeftInset
                focus: true

                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Escape) {
                        controller.dismissTopLayer(appHeader.paletteVisible);
                        event.accepted = true;
                    }
                }

                ColumnLayout {
                    anchors.fill: parent
                    spacing: theme.smallGap

                    AppHeader {
                        id: appHeader
                        objectName: "xrayAppHeader"
                        theme: theme
                        catalog: controller.catalog
                        capabilities: controller.capabilities
                        snapshot: controller.snapshot
                        offline: controller.offline
                        interactionEnabled: !controller.interactionBlocked
                        onSearchAccepted: function(query) { controller.inspect(query); }
                        onCatalogRequested: controller.requestCatalog()
                        onPickRequested: controller.pickWindow()
                        onPauseRequested: controller.toggleSampling()
                        onCapsuleRequested: controller.toggleDrawer(controller.capsuleDrawer)
                        onSettingsRequested: {
                            settingsDrawer.openWith(controller.currentSettings);
                            controller.toggleDrawer(controller.settingsDrawer);
                        }
                        onCloseRequested: controller.close()
                    }

                    IdentityBar {
                        Layout.fillWidth: true
                        theme: theme
                        snapshot: controller.snapshot
                        previousMetrics: controller.previousMetrics
                        onAlternativesRequested: controller.showDetails(DetailDomains.Alternatives)
                        onCoverageRequested: if (controller.snapshot.coverage) controller.showDetails(DetailDomains.Coverage)
                    }

                    DashboardGrid {
                        objectName: "xrayDashboard"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        theme: theme
                        snapshot: controller.snapshot
                        cpuSamples: controller.cpuSamples
                        memorySamples: controller.memorySamples
                        performanceWindowSeconds: controller.performanceWindowSeconds
                        busy: controller.busy
                        onProcessSelected: function(pid) { controller.focusProcess(pid); }
                        onDetailsRequested: function(domain) { controller.showDetails(domain); }
                    }

                    FooterBar {
                        objectName: "xrayFooter"
                        Layout.fillWidth: true
                        theme: theme
                        snapshot: controller.snapshot
                        offline: controller.offline
                        actionsEnabled: !controller.interactionBlocked
                        onResetRequested: controller.resetBaseline()
                        onActionRequested: function(action) { controller.requestAction(action); }
                    }
                }

                Rectangle {
                    visible: controller.drawer !== ""
                    z: 40
                    anchors.fill: parent
                    color: theme.drawerScrim
                    MouseArea { anchors.fill: parent; onClicked: controller.dismissDrawerAfterPointer() }
                }

                DetailDrawer {
                    id: detailDrawer
                    objectName: "xrayDetailDrawer"
                    visible: controller.drawer === controller.detailsDrawer
                    z: 41
                    width: Math.min(620, parent.width * 0.46)
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    theme: theme
                    snapshot: controller.detailSnapshot
                    domain: controller.detailDomain
                    selectionEnabled: !controller.offline
                    onVisibleChanged: if (visible) filterText = ""
                    onClosed: controller.dismissDrawerAfterPointer()
                    onProcessSelected: function(pid) { controller.selectProcessAfterPointer(pid); }
                }

                SettingsDrawer {
                    id: settingsDrawer
                    objectName: "xraySettingsDrawer"
                    visible: controller.drawer === controller.settingsDrawer
                    z: 41
                    width: Math.min(480, parent.width * 0.4)
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    theme: theme
                    schema: controller.settingsSpec
                    defaults: controller.defaultSettings
                    onClosed: controller.dismissDrawerAfterPointer()
                    onApplied: function(values) { controller.configure(values); }
                }

                CapsuleDrawer {
                    id: capsuleDrawer
                    objectName: "xrayCapsuleDrawer"
                    visible: controller.drawer === controller.capsuleDrawer
                    z: 41
                    width: Math.min(480, parent.width * 0.4)
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    theme: theme
                    offline: controller.offline
                    onClosed: controller.dismissDrawerAfterPointer()
                    onExportRequested: controller.exportCapsule()
                    onReportRequested: controller.copyReport()
                    onOpenRequested: function(path) { controller.openCapsule(path); }
                    onCompareRequested: function(path) { controller.compareCapsule(path); }
                }

                ConfirmationOverlay {
                    z: 60
                    anchors.fill: parent
                    theme: theme
                    action: controller.pendingAction
                    onCancelled: controller.cancelActionAfterPointer()
                    onConfirmed: function(actionId) {
                        controller.confirmActionAfterPointer(
                            actionId,
                            Number((controller.pendingAction || {}).expectedInspectionId || 0)
                        );
                    }
                }

                NoticeToast {
                    z: 70
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 16
                    theme: theme
                    message: controller.notice
                }
            }
        }
    }
}
