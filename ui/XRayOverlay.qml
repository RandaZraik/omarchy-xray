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
    property var appLibrary: null
    property var inspectionScreen: null
    property string currentQuery: ""
    property bool browserOpen: true
    readonly property bool dashboardInteractive: controller.drawer === ""
        && !controller.pendingAction

    function open(payloadJson) {
        inspectionScreen = focusedScreen();
        browserOpen = true;
        controller.open(payloadJson);
    }
    function close() { controller.close(); }

    function browse() {
        browserOpen = true;
        Qt.callLater(function() { targetBrowser.focusSearch(true); });
    }

    function toggleBrowser() {
        if (browserOpen) {
            browserOpen = false;
            return;
        }
        browse();
    }

    function showDetails(domain) {
        if (domain) controller.showDetails(domain);
    }

    function dismissTopLayer() {
        if (controller.pendingAction) controller.cancelActionAfterPointer();
        else if (controller.drawer) controller.closeDrawer();
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
        onClosed: root.inspectionScreen = null
        onQuerySynchronized: function(query) {
            root.currentQuery = query;
        }
        onClipboardRequested: function(text) { Quickshell.clipboardText = text; }
        onCapsuleStatusChanged: function(message) { capsuleDrawer.status = message; }
    }

    XRayTheme { id: theme }
    XRayContract { id: contract }

    Shortcut {
        sequence: "Escape"
        context: Qt.ApplicationShortcut
        enabled: controller.opened
        onActivated: root.dismissTopLayer()
    }

    Shortcut {
        sequence: "Ctrl+K"
        context: Qt.ApplicationShortcut
        enabled: controller.opened && root.dashboardInteractive
        onActivated: root.browse()
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
        MouseArea {
            objectName: "xrayBackdropDismissArea"
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.dismissTopLayer()
        }

        Rectangle {
            width: desk.width + theme.gap * 2
            height: desk.height + theme.gap * 2
            anchors.centerIn: parent
            radius: theme.panelRadius + theme.gap
            color: theme.transparent
            border.color: theme.accentGlow
            border.width: theme.borderWidth
            opacity: 0.48
        }

        BorderSurface {
            id: desk
            objectName: "xrayDesk"
            width: Math.min(theme.panelMaxWidth, panel.width - theme.outerGap * 2)
            height: Math.min(theme.panelMaxHeight, panel.height - theme.outerGap * 2)
            anchors.centerIn: parent
            radius: theme.panelRadius
            borderSpec: Commons.Border.flat(theme.accentBorder, theme.borderWidth)
            padding: theme.panelPadding
            color: theme.panel

            MouseArea {
                objectName: "xrayDeskInputBarrier"
                anchors.fill: parent
                onClicked: function(mouse) { mouse.accepted = true; }
            }

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
                    spacing: theme.consoleGap

                    AppHeader {
                        id: appHeader
                        objectName: "xrayAppHeader"
                        theme: theme
                        capabilities: controller.capabilities
                        snapshot: controller.snapshot
                        browserOpen: root.browserOpen
                        offline: controller.offline
                        interactionEnabled: !controller.interactionBlocked
                        onBrowserRequested: root.toggleBrowser()
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

                        TargetBrowser {
                            id: targetBrowser
                            z: 1
                            visible: root.browserOpen
                            enabled: root.dashboardInteractive
                            width: theme.targetBrowserWidth
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
                            enabled: root.dashboardInteractive
                            anchors.top: parent.top
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.left: parent.left
                            anchors.leftMargin: root.browserOpen
                                ? theme.targetBrowserWidth + theme.consoleGap : 0
                            spacing: theme.consoleGap

                            IdentityBar {
                                Layout.fillWidth: true
                                theme: theme
                                appLibrary: root.appLibrary
                                snapshot: controller.snapshot
                                performanceSamples: controller.performanceSamples
                                performanceWindowSeconds: controller.performanceWindowSeconds
                                onAlternativesRequested: controller.showDetails(DetailDomains.Alternatives)
                                onCoverageRequested: if (controller.snapshot.coverage) controller.showDetails(DetailDomains.Coverage)
                            }

                            DashboardGrid {
                                objectName: "xrayDashboard"
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                theme: theme
                                snapshot: controller.snapshot
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
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: controller.dismissDrawerAfterPointer()
                    }
                }

                DetailDrawer {
                    id: detailDrawer
                    objectName: "xrayDetailDrawer"
                    visible: controller.drawer === controller.detailsDrawer
                    z: 41
                    width: controller.detailDomain === DetailDomains.Processes
                        ? Math.min(720, parent.width * 0.52)
                        : Math.min(580, parent.width * 0.42)
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    anchors.topMargin: theme.drawerMargin
                    anchors.bottomMargin: theme.drawerMargin
                    anchors.rightMargin: theme.drawerMargin
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
                    width: Math.min(520, parent.width * 0.44)
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    anchors.topMargin: theme.drawerMargin
                    anchors.bottomMargin: theme.drawerMargin
                    anchors.rightMargin: theme.drawerMargin
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
                    width: Math.min(520, parent.width * 0.44)
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    anchors.topMargin: theme.drawerMargin
                    anchors.bottomMargin: theme.drawerMargin
                    anchors.rightMargin: theme.drawerMargin
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
