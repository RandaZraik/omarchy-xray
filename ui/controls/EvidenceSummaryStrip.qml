import QtQuick

Rectangle {
    id: root

    required property var theme
    property var stats: []
    property color accentColor: theme.accent

    implicitHeight: theme.drawerSummaryHeight
    radius: theme.controlRadius
    color: theme.quietSurface

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.theme.telemetryRailWidth
        radius: root.theme.pillRadius
        color: root.accentColor
    }

    Row {
        anchors.fill: parent
        anchors.leftMargin: root.theme.gap

        Repeater {
            model: root.stats

            delegate: Item {
                required property var modelData
                required property int index
                width: (root.width - root.theme.gap) / root.stats.length
                height: root.height

                SummaryMetric {
                    anchors.fill: parent
                    theme: root.theme
                    label: String(parent.modelData.label || "")
                    value: String(parent.modelData.value || "")
                    accentColor: parent.modelData.tone
                        ? root.theme.toneColor(parent.modelData.tone)
                        : root.accentColor
                }

                Rectangle {
                    visible: parent.index < root.stats.length - 1
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: root.theme.dividerWidth
                    height: parent.height - root.theme.gap * 2
                    color: root.theme.cardBorder
                    opacity: root.theme.subtleDividerOpacity
                }
            }
        }
    }
}
