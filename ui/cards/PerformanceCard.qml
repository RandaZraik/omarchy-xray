import QtQuick
import QtQuick.Layouts
import "../controls"

Card {
    id: root
    objectName: "xrayPerformanceCard"

    property var samples: []
    property int windowSeconds: 60
    readonly property int sampleCount: samples.length
    readonly property double firstCapturedAt: sampleCount
        ? Number(samples[0].capturedAt || 0) : 0
    readonly property double latestCapturedAt: sampleCount
        ? Number(samples[sampleCount - 1].capturedAt || 0) : 0
    readonly property real historySeconds: sampleCount > 1
        ? Math.min(windowSeconds, Math.max(0, latestCapturedAt - firstCapturedAt) / 1000)
        : 0
    title: "Performance · last " + windowSeconds + " seconds"
    countText: sampleCount > 1
        ? Math.round(historySeconds) + "S CAPTURED"
        : "LIVE SAMPLE"

    onSamplesChanged: chart.requestPaint()

    body: Item {
        anchors.fill: parent

        Row {
            id: legend
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            height: root.theme.performanceLegendHeight
            spacing: root.theme.gap

            Repeater {
                model: [
                    {"label": "CPU", "color": root.theme.cpuAccent},
                    {"label": "MEMORY", "color": root.theme.memoryAccent}
                ]

                delegate: Row {
                    required property var modelData
                    height: legend.height
                    spacing: root.theme.smallGap

                    Rectangle {
                        width: root.theme.performanceLegendSwatchWidth
                        height: root.theme.telemetrySignalHeight
                        anchors.verticalCenter: parent.verticalCenter
                        color: modelData.color
                    }

                    PlainText {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label
                        color: root.theme.muted
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.captionFontSize
                        font.letterSpacing: root.theme.labelTracking
                    }
                }
            }
        }

        Canvas {
            id: chart
            objectName: "xrayPerformanceChart"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: legend.bottom
            anchors.bottom: timeline.top
            anchors.bottomMargin: root.theme.smallGap
            antialiasing: true

            onPaint: {
                var context = getContext("2d");
                context.reset();
                context.lineWidth = 1;
                context.strokeStyle = root.theme.withAlpha(
                    root.theme.grid, root.theme.performanceGridOpacity
                );
                for (var grid = 1; grid < 3; grid++) {
                    var gridY = grid * height / 3;
                    context.beginPath();
                    context.moveTo(0, gridY);
                    context.lineTo(width, gridY);
                    context.stroke();
                }
                for (var tick = 1; tick < 4; tick++) {
                    var tickX = tick * width / 4;
                    context.beginPath();
                    context.moveTo(tickX, 0);
                    context.lineTo(tickX, height);
                    context.stroke();
                }

                var cpuMaximum = 0;
                var memoryMinimum = Infinity;
                var memoryMaximum = -Infinity;
                for (var sampleIndex = 0; sampleIndex < root.samples.length; sampleIndex++) {
                    var sample = root.samples[sampleIndex] || {};
                    if (sample.cpuPercent !== null && sample.cpuPercent !== undefined) {
                        var cpu = Number(sample.cpuPercent);
                        if (Number.isFinite(cpu)) cpuMaximum = Math.max(cpuMaximum, cpu);
                    }
                    var memory = Number(sample.memoryBytes);
                    if (Number.isFinite(memory)) {
                        memoryMinimum = Math.min(memoryMinimum, memory);
                        memoryMaximum = Math.max(memoryMaximum, memory);
                    }
                }
                cpuMaximum = Math.max(
                    root.theme.minimumCpuChartScale,
                    cpuMaximum * root.theme.performanceScaleHeadroom
                );
                root.drawSeries(
                    context, "cpuPercent", 0, cpuMaximum,
                    root.theme.trace, root.theme.performancePrimaryTraceWidth
                );

                if (!Number.isFinite(memoryMinimum)) memoryMinimum = 0;
                if (!Number.isFinite(memoryMaximum)) memoryMaximum = memoryMinimum;
                var memoryPadding = Math.max(
                    1,
                    memoryMaximum * root.theme.performanceMemoryPadding
                );
                root.drawSeries(
                    context, "memoryBytes",
                    memoryMinimum - memoryPadding,
                    memoryMaximum + memoryPadding,
                    root.theme.secondaryTrace,
                    root.theme.performanceSecondaryTraceWidth
                );
            }
        }

        Item {
            id: timeline
            objectName: "xrayPerformanceTimeline"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: root.theme.performanceTimelineHeight

            PlainText {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: "−" + root.windowSeconds + "S"
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.captionFontSize
            }

            PlainText {
                anchors.centerIn: parent
                text: root.sampleCount < 2
                    ? "BUILDING HISTORY"
                    : Math.round(root.historySeconds) + "S OF " + root.windowSeconds + "S"
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.captionFontSize
                font.letterSpacing: root.theme.utilityTracking
            }

            PlainText {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: "NOW"
                color: root.theme.text
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.captionFontSize
                font.bold: true
            }
        }
    }

    function drawSeries(context, field, minimum, maximum, color, lineWidth) {
        if (!samples.length) return;
        var range = Math.max(1, maximum - minimum);
        var plotLeft = root.theme.performancePointRadius;
        var plotRight = chart.width - root.theme.performancePointRadius;
        var plotWidth = Math.max(0, plotRight - plotLeft);
        var segments = [];
        var segment = [];
        for (var index = 0; index < samples.length; index++) {
            var sample = samples[index] || {};
            var rawValue = sample[field];
            var capturedAt = Number(sample.capturedAt || 0);
            var numeric = Number(rawValue);
            if (rawValue === null || rawValue === undefined
                    || !Number.isFinite(numeric) || capturedAt <= 0) {
                if (segment.length) segments.push(segment);
                segment = [];
                continue;
            }
            var ageSeconds = Math.min(
                root.windowSeconds,
                Math.max(0, root.latestCapturedAt - capturedAt) / 1000
            );
            segment.push(
                plotRight - ageSeconds / Math.max(1, root.windowSeconds) * plotWidth,
                chart.height
                    - (Math.max(minimum, Math.min(maximum, numeric)) - minimum) / range
                        * (chart.height - root.theme.performancePlotPadding * 2)
                    - root.theme.performancePlotPadding
            );
        }
        if (segment.length) segments.push(segment);
        if (!segments.length) return;

        var fill = context.createLinearGradient(0, 0, 0, chart.height);
        fill.addColorStop(0, root.theme.withAlpha(color, root.theme.performanceFillOpacity));
        fill.addColorStop(1, root.theme.withAlpha(color, 0));

        context.strokeStyle = color;
        context.lineWidth = lineWidth;
        context.lineJoin = "round";
        context.lineCap = "round";
        for (var segmentIndex = 0; segmentIndex < segments.length; segmentIndex++) {
            var points = segments[segmentIndex];
            if (points.length > 2) {
                context.fillStyle = fill;
                context.beginPath();
                context.moveTo(points[0], chart.height);
                context.lineTo(points[0], points[1]);
                for (var fillIndex = 2; fillIndex < points.length; fillIndex += 2)
                    context.lineTo(points[fillIndex], points[fillIndex + 1]);
                context.lineTo(points[points.length - 2], chart.height);
                context.closePath();
                context.fill();
            }

            context.beginPath();
            context.moveTo(points[0], points[1]);
            for (var pointIndex = 2; pointIndex < points.length; pointIndex += 2)
                context.lineTo(points[pointIndex], points[pointIndex + 1]);
            context.stroke();
        }

        var latest = samples[samples.length - 1] || {};
        var latestValue = latest[field];
        var lastSegment = segments[segments.length - 1];
        if (latestValue === null || latestValue === undefined
                || !Number.isFinite(Number(latestValue))) return;
        context.fillStyle = color;
        context.beginPath();
        context.arc(
            lastSegment[lastSegment.length - 2],
            lastSegment[lastSegment.length - 1],
            root.theme.performancePointRadius,
            0,
            Math.PI * 2
        );
        context.fill();
    }
}
