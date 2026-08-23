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
    property bool browserOpen: false
    property string currentQuery: ""
    readonly property bool browserPinned: desk.width >= theme.targetBrowserPinnedWidth

    function open(payloadJson) {
        inspectionScreen = focusedScreen();
        controller.open(payloadJson);
    }
    function close() { controller.close(); }

    function dismissTopLayer() {
        if (controller.pendingAction) controller.cancelActionAfterPointer();
        else if (controller.drawer) controller.closeDrawer();
        else if (browserOpen && !browserPinned) browserOpen = false;
        else controller.close();
    }

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
        onOpenedChanged: if (opened) {
            Qt.callLater(function() { root.browserOpen = root.browserPinned; });
        }
        onClosed: root.inspectionScreen = null
        onQuerySynchronized: function(query) {
            root.currentQuery = query;
        }
        onClipboardRequested: function(text) { Quickshell.clipboardText = text; }
        onCapsuleStatusChanged: function(message) { capsuleDrawer.status = message; }
    }

    XRayTheme { id: theme }
    XRayContract { id: contract }

    onBrowserPinnedChanged: if (controller.opened && browserPinned)
        browserOpen = true

    Shortcut {
        sequence: "Escape"
        context: Qt.ApplicationShortcut
        enabled: controller.opened
        onActivated: root.dismissTopLayer()
    }

    Shortcut {
        sequence: "Ctrl+K"
        context: Qt.ApplicationShortcut
        enabled: controller.opened && controller.drawer === "" && !controller.pendingAction
        onActivated: {
            root.browserOpen = true;
            Qt.callLater(function() { targetBrowser.focusSearch(true); });
        }
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
                        root.dismissTopLayer();
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
                        capabilities: controller.capabilities
                        snapshot: controller.snapshot
                        offline: controller.offline
                        interactionEnabled: !controller.interactionBlocked
                        browserVisible: root.browserOpen
                        onBrowserRequested: {
                            root.browserOpen = !root.browserOpen;
                            if (root.browserOpen)
                                Qt.callLater(function() { targetBrowser.focusSearch(false); });
                        }
                        onPickRequested: controller.pickWindow()
                        onPauseRequested: controller.toggleSampling()
                        onCapsuleRequested: controller.toggleDrawer(controller.capsuleDrawer)
                        onSettingsRequested: {
                            settingsDrawer.openWith(controller.currentSettings);
                            controller.toggleDrawer(controller.settingsDrawer);
                        }
                        onCloseRequested: controller.close()
                    }

                    Item {
                        id: workspace
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Rectangle {
                            visible: root.browserOpen && !root.browserPinned
                            z: 20
                            anchors.fill: parent
                            color: theme.drawerScrim
                            TapHandler { onTapped: root.browserOpen = false }
                        }

                        TargetBrowser {
                            id: targetBrowser
                            z: root.browserPinned ? 0 : 21
                            visible: root.browserOpen
                            width: root.browserPinned
                                ? Math.min(theme.targetBrowserWidth, workspace.width * 0.28)
                                : Math.min(theme.targetBrowserOverlayWidth, workspace.width * 0.86)
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            anchors.left: parent.left
                            theme: theme
                            catalog: controller.catalog
                            target: controller.snapshot.target || ({})
                            currentQuery: root.currentQuery
                            interactionEnabled: !controller.interactionBlocked
                            catalogLoading: controller.catalogRequested
                            closable: true
                            onSelected: function(query) { controller.inspect(query); }
                            onCatalogRequested: controller.requestCatalog()
                            onCloseRequested: root.browserOpen = false
                        }

                        ColumnLayout {
                            id: dashboardColumn
                            anchors.top: parent.top
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.left: parent.left
                            anchors.leftMargin: root.browserOpen && root.browserPinned
                                ? targetBrowser.width + theme.smallGap : 0
                            spacing: theme.smallGap

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
                                performanceSamples: controller.performanceSamples
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
