import QtQuick
import QtQuick.Layouts
import "../controls"

Item {
    id: root
    objectName: "xrayTelemetryTrace"

    required property var theme
    property var samples: []
    property int windowSeconds: 60

    readonly property int sampleCount: samples.length
    readonly property double firstCapturedAt: sampleCount
        ? Number(samples[0].capturedAt || 0) : 0
    readonly property double latestCapturedAt: sampleCount
        ? Number(samples[sampleCount - 1].capturedAt || 0) : 0
    readonly property int historySeconds: sampleCount > 1
        ? Math.round(Math.min(
            windowSeconds,
            Math.max(0, latestCapturedAt - firstCapturedAt) / 1000
        )) : 0

    clip: true

    RowLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: root.theme.smallGap
        anchors.rightMargin: root.theme.smallGap
        height: root.theme.telemetryTraceHeaderHeight
        spacing: root.theme.smallGap

        PlainText {
            text: "60S TRACE"
            color: root.theme.sectionText
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            font.bold: true
            font.letterSpacing: root.theme.utilityTracking
        }

        Item { Layout.fillWidth: true }

        Repeater {
            model: [
                {"label": "CPU", "color": root.theme.cpuAccent},
                {"label": "MEM", "color": root.theme.memoryAccent}
            ]
            delegate: Row {
                required property var modelData
                spacing: 2
                Rectangle {
                    width: 9
                    height: root.theme.telemetrySignalHeight
                    anchors.verticalCenter: parent.verticalCenter
                    color: parent.modelData.color
                }
                PlainText {
                    text: parent.modelData.label
                    color: root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                }
            }
        }

        PlainText {
            text: root.sampleCount > 1 ? root.historySeconds + "S" : "LIVE"
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
        }
    }

    PerformancePlot {
        objectName: "xrayTelemetryChart"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: timeline.top
        anchors.leftMargin: root.theme.smallGap
        anchors.rightMargin: root.theme.smallGap
        anchors.topMargin: root.theme.telemetryTraceHeaderHeight
        anchors.bottomMargin: 1
        theme: root.theme
        samples: root.samples
        windowSeconds: root.windowSeconds
    }

    Item {
        id: timeline
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: root.theme.telemetryTraceTimelineHeight

        PlainText {
            anchors.left: parent.left
            anchors.leftMargin: root.theme.smallGap
            anchors.verticalCenter: parent.verticalCenter
            text: "−" + root.windowSeconds + "S"
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
        }
        PlainText {
            anchors.right: parent.right
            anchors.rightMargin: root.theme.smallGap
            anchors.verticalCenter: parent.verticalCenter
            text: "NOW"
            color: root.theme.text
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            font.bold: true
        }
    }
}
