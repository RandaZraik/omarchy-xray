import QtQuick
import QtQuick.Layouts
import "../controls"
import "../Format.js" as Format

Item {
    id: root

    required property var theme
    property var snapshot: ({})
    property var previousMetrics: ({})
    signal alternativesRequested()
    signal coverageRequested()

    readonly property var target: snapshot.target || {}
    readonly property var metrics: snapshot.metrics || {}
    readonly property var trail: target.trail || []
    readonly property string origin: trail.length
        ? String(trail[0].label || target.label || "Target")
        : String(target.label || "Select a target")
    readonly property string owner: trail.length > 1
        ? String(trail[trail.length - 1].label || target.label || "") : ""

    function delta(name, suffix) {
        if (previousMetrics[name] === undefined) return "collecting baseline";
        if (metrics[name] === null || metrics[name] === undefined
                || previousMetrics[name] === null) return "unavailable";
        var change = Number(metrics[name] || 0) - Number(previousMetrics[name] || 0);
        return (change > 0 ? "+" : "") + Format.number(change, 1) + suffix;
    }

    function cpuDetail() {
        if (metrics.cpuStatus === "unavailable") return "unavailable";
        if (metrics.cpuStatus === "baseline") return "collecting baseline";
        return delta("cpuPercent", "%");
    }

    function ioDetail() {
        if (metrics.ioStatus === "unavailable") return "unavailable";
        if (metrics.ioStatus === "baseline") return "collecting baseline";
        return "read + write";
    }

    height: theme.telemetryHeight

    Rectangle {
        anchors.fill: parent
        radius: root.theme.cardRadius
        color: root.theme.surfaceMid
        border.color: root.theme.cardBorder
        border.width: root.theme.borderWidth

        AccentSignal {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: root.theme.borderWidth
            theme: root.theme
            fadePosition: 0.36
            radius: root.theme.cardRadius
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: root.theme.borderWidth
            spacing: 0

            Item {
                Layout.fillHeight: true
                Layout.preferredWidth: root.theme.telemetryTargetWidth
                Layout.minimumWidth: root.theme.telemetryTargetMinimumWidth

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: root.theme.telemetryModulePadding
                    anchors.rightMargin: root.theme.telemetryModulePadding
                    spacing: root.theme.gap

                    Rectangle {
                        Layout.alignment: Qt.AlignVCenter
                        width: 9
                        height: 9
                        radius: root.theme.pillRadius
                        color: root.theme.accent

                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.width + root.theme.gap
                            height: width
                            radius: root.theme.pillRadius
                            color: root.theme.accentGlow
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 3

                        PlainText {
                            Layout.fillWidth: true
                            text: "SELECTED SIGNAL"
                            color: root.theme.accent
                            font.family: root.theme.dataFont
                            font.pixelSize: root.theme.microFontSize
                            font.bold: true
                            font.letterSpacing: root.theme.utilityTracking
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: root.theme.smallGap

                            PlainText {
                                Layout.preferredWidth: root.owner ? 136 : -1
                                Layout.fillWidth: root.owner === ""
                                text: root.origin
                                color: root.owner ? root.theme.muted : root.theme.text
                                font.family: root.theme.bodyFont
                                font.pixelSize: root.theme.summaryFontSize
                                font.bold: root.owner === ""
                                elide: Text.ElideRight
                            }
                            PlainText {
                                visible: root.owner !== ""
                                text: "›"
                                color: root.theme.accent
                                font.family: root.theme.dataFont
                                font.pixelSize: root.theme.summaryFontSize
                            }
                            PlainText {
                                visible: root.owner !== ""
                                Layout.fillWidth: true
                                text: root.owner
                                color: root.theme.text
                                font.family: root.theme.bodyFont
                                font.pixelSize: root.theme.summaryFontSize
                                font.bold: true
                                elide: Text.ElideRight
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: root.theme.gap

                            PlainText {
                                visible: (root.target.alternatives || []).length > 1
                                text: (root.target.alternatives || []).length
                                    + " matching processes"
                                color: alternativesHover.hovered
                                    ? root.theme.text : root.theme.muted
                                font.family: root.theme.dataFont
                                font.pixelSize: root.theme.captionFontSize
                                HoverHandler { id: alternativesHover }
                                TapHandler { onTapped: root.alternativesRequested() }
                            }
                            PlainText {
                                text: String((root.snapshot.coverage || {}).status || "")
                                color: coverageHover.hovered
                                    ? root.theme.text
                                    : (root.snapshot.coverage || {}).statusCode === "full"
                                        ? root.theme.muted : root.theme.danger
                                font.family: root.theme.dataFont
                                font.pixelSize: root.theme.captionFontSize
                                HoverHandler { id: coverageHover }
                                TapHandler { onTapped: root.coverageRequested() }
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillHeight: true
                Layout.topMargin: root.theme.pad
                Layout.bottomMargin: root.theme.pad
                width: root.theme.dividerWidth
                color: root.theme.cardBorder
            }

            Repeater {
                model: [
                    {"label": "CPU", "value": Format.percent(root.metrics.cpuPercent), "detail": root.cpuDetail(), "accent": root.theme.cpuAccent},
                    {"label": "Memory", "value": Format.bytes(root.metrics.memoryBytes), "detail": (root.metrics.threads || 0) + " threads", "accent": root.theme.memoryAccent},
                    {"label": "Disk I/O", "value": root.metrics.ioAvailable === false ? "—" : Format.rate(Number(root.metrics.readBytesPerSecond || 0) + Number(root.metrics.writeBytesPerSecond || 0)), "detail": root.ioDetail(), "accent": root.theme.storageAccent},
                    {"label": "GPU", "value": Format.percent(root.metrics.gpuPercent), "detail": ((root.snapshot.devices || {}).gpu || []).length + " DRM clients", "accent": root.theme.deviceAccent},
                    {"label": "Uptime", "value": Format.duration(root.metrics.uptimeSeconds), "detail": root.metrics.uptimeSeconds === null || root.metrics.uptimeSeconds === undefined ? "unavailable" : root.snapshot.samplingPaused ? "sampling paused" : "live sample", "accent": root.theme.runtimeAccent}
                ]

                delegate: Item {
                    required property int index
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredWidth: root.theme.telemetryMetricWidth
                    Layout.minimumWidth: root.theme.telemetryMetricMinimumWidth
                    Layout.fillHeight: true

                    Rectangle {
                        visible: parent.index > 0
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.topMargin: root.theme.pad
                        anchors.bottomMargin: root.theme.pad
                        width: root.theme.dividerWidth
                        color: root.theme.cardBorder
                    }

                    SummaryMetric {
                        anchors.fill: parent
                        theme: root.theme
                        label: parent.modelData.label
                        value: parent.modelData.value
                        detail: parent.modelData.detail
                        accentColor: parent.modelData.accent
                    }
                }
            }
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: root.theme.borderWidth
            radius: Math.max(0, parent.radius - root.theme.borderWidth)
            color: root.theme.transparent
            border.color: root.theme.surfaceHighlight
            border.width: root.theme.dividerWidth
            opacity: 0.42
        }
    }
}
