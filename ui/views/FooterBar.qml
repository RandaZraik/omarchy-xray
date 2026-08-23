import QtQuick
import QtQuick.Layouts
import qs.Ui
import "../controls"
import "../Format.js" as Format

Rectangle {
    id: root

    required property var theme
    property var snapshot: ({})
    property bool offline: false
    property bool actionsEnabled: true
    readonly property bool expandedStatus: width >= theme.footerExpandedWidth
    signal actionRequested(var action)
    signal resetRequested()

    function changeCount() {
        var domains = (snapshot.changes || {}).domains || {};
        var total = 0;
        for (var name in domains) {
            var change = domains[name] || {"added": 0, "removed": 0};
            total += Number(change.added || 0) + Number(change.removed || 0);
        }
        return total;
    }

    height: 46
    radius: theme.radius
    color: theme.quietSurface
    border.color: theme.accentBorder
    border.width: theme.borderWidth

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: root.theme.footerSidePadding
        anchors.rightMargin: root.theme.footerSidePadding
        spacing: root.theme.footerSpacing

        Rectangle {
            width: 7
            height: 7
            radius: 4
            color: root.offline || root.snapshot.samplingPaused ? root.theme.muted : root.theme.accent
        }
        PlainText {
            text: root.offline ? "OFFLINE REPORT" : (root.snapshot.samplingPaused ? "PAUSED" : "LIVE")
            color: root.theme.text
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
            font.letterSpacing: root.theme.utilityTracking
        }
        PlainText {
            visible: root.expandedStatus
            text: "SINCE OPENED"
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
            font.letterSpacing: root.theme.utilityTracking
            Layout.leftMargin: 8
        }
        PlainText {
            visible: root.expandedStatus
            readonly property int total: root.changeCount()
            text: total ? total + (total === 1 ? " CHANGE" : " CHANGES") : "NO CHANGES"
            color: total ? root.theme.text : root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
        }
        IconButton {
            iconName: "baseline"
            tooltipText: "Start a new comparison baseline"
            enabled: root.actionsEnabled && !root.offline
                && !!(root.snapshot.target && root.snapshot.target.rootPid)
            onClicked: root.resetRequested()
        }
        Item { Layout.fillWidth: true }
        Repeater {
            model: root.snapshot.actions || []
            delegate: Button {
                required property var modelData
                text: modelData.label
                iconText: Format.icon(modelData.icon)
                tooltipText: modelData.label
                bordered: true
                focusable: true
                enabled: root.actionsEnabled && modelData.available === true && !root.offline
                opacity: enabled ? 1 : root.theme.disabledOpacity
                horizontalPadding: 9
                verticalPadding: 6
                iconSize: 11
                fontSize: root.theme.captionFontSize
                onClicked: root.actionRequested(modelData)
            }
        }
    }
}
