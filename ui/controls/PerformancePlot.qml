import QtQuick

Item {
    id: root

    required property var theme
    property var samples: []
    property int windowSeconds: 60
    property bool gridVisible: true

    readonly property int sampleCount: samples.length
    readonly property double latestCapturedAt: sampleCount
        ? Number(samples[sampleCount - 1].capturedAt || 0) : 0

    onSamplesChanged: chart.requestPaint()
    onWidthChanged: chart.requestPaint()
    onHeightChanged: chart.requestPaint()

    function requestPaint() { chart.requestPaint() }

    Canvas {
        id: chart
        anchors.fill: parent
        antialiasing: true

        onPaint: {
            var context = getContext("2d")
            context.reset()
            if (root.gridVisible) root.drawGrid(context)

            var cpuMaximum = 0
            var memoryMinimum = Infinity
            var memoryMaximum = -Infinity
            for (var index = 0; index < root.samples.length; index++) {
                var sample = root.samples[index] || {}
                if (sample.cpuPercent !== null && sample.cpuPercent !== undefined) {
                    var cpu = Number(sample.cpuPercent)
                    if (Number.isFinite(cpu)) cpuMaximum = Math.max(cpuMaximum, cpu)
                }
                var memory = Number(sample.memoryBytes)
                if (Number.isFinite(memory)) {
                    memoryMinimum = Math.min(memoryMinimum, memory)
                    memoryMaximum = Math.max(memoryMaximum, memory)
                }
            }
            cpuMaximum = Math.max(
                root.theme.minimumCpuChartScale,
                cpuMaximum * root.theme.performanceScaleHeadroom
            )
            root.drawSeries(
                context, "cpuPercent", 0, cpuMaximum,
                root.theme.trace, root.theme.performancePrimaryTraceWidth
            )

            if (!Number.isFinite(memoryMinimum)) memoryMinimum = 0
            if (!Number.isFinite(memoryMaximum)) memoryMaximum = memoryMinimum
            var memoryPadding = Math.max(
                1, memoryMaximum * root.theme.performanceMemoryPadding
            )
            root.drawSeries(
                context, "memoryBytes", memoryMinimum - memoryPadding,
                memoryMaximum + memoryPadding, root.theme.secondaryTrace,
                root.theme.performanceSecondaryTraceWidth
            )
        }
    }

    function drawGrid(context) {
        context.lineWidth = 1
        context.strokeStyle = root.theme.withAlpha(
            root.theme.grid, root.theme.performanceGridOpacity
        )
        for (var row = 1; row < 3; row++) {
            var y = row * height / 3
            context.beginPath()
            context.moveTo(0, y)
            context.lineTo(width, y)
            context.stroke()
        }
        for (var column = 1; column < 4; column++) {
            var x = column * width / 4
            context.beginPath()
            context.moveTo(x, 0)
            context.lineTo(x, height)
            context.stroke()
        }
    }

    function drawSeries(context, field, minimum, maximum, color, lineWidth) {
        if (!samples.length) return
        var range = Math.max(1, maximum - minimum)
        var plotLeft = root.theme.performancePointRadius
        var plotRight = chart.width - root.theme.performancePointRadius
        var plotWidth = Math.max(0, plotRight - plotLeft)
        var segments = []
        var segment = []
        for (var index = 0; index < samples.length; index++) {
            var sample = samples[index] || {}
            var rawValue = sample[field]
            var capturedAt = Number(sample.capturedAt || 0)
            var numeric = Number(rawValue)
            if (rawValue === null || rawValue === undefined
                    || !Number.isFinite(numeric) || capturedAt <= 0) {
                if (segment.length) segments.push(segment)
                segment = []
                continue
            }
            var ageSeconds = Math.min(
                root.windowSeconds,
                Math.max(0, root.latestCapturedAt - capturedAt) / 1000
            )
            segment.push(
                plotRight - ageSeconds / Math.max(1, root.windowSeconds) * plotWidth,
                chart.height
                    - (Math.max(minimum, Math.min(maximum, numeric)) - minimum) / range
                        * (chart.height - root.theme.performancePlotPadding * 2)
                    - root.theme.performancePlotPadding
            )
        }
        if (segment.length) segments.push(segment)
        if (!segments.length) return

        var fill = context.createLinearGradient(0, 0, 0, chart.height)
        fill.addColorStop(
            0, root.theme.withAlpha(color, root.theme.performanceFillOpacity)
        )
        fill.addColorStop(1, root.theme.withAlpha(color, 0))
        context.strokeStyle = color
        context.lineWidth = lineWidth
        context.lineJoin = "round"
        context.lineCap = "round"
        for (var segmentIndex = 0; segmentIndex < segments.length; segmentIndex++) {
            var points = segments[segmentIndex]
            if (points.length > 2) {
                context.fillStyle = fill
                context.beginPath()
                context.moveTo(points[0], chart.height)
                context.lineTo(points[0], points[1])
                for (var fillIndex = 2; fillIndex < points.length; fillIndex += 2)
                    context.lineTo(points[fillIndex], points[fillIndex + 1])
                context.lineTo(points[points.length - 2], chart.height)
                context.closePath()
                context.fill()
            }

            context.beginPath()
            context.moveTo(points[0], points[1])
            for (var pointIndex = 2; pointIndex < points.length; pointIndex += 2)
                context.lineTo(points[pointIndex], points[pointIndex + 1])
            context.stroke()
        }

        var latest = samples[samples.length - 1] || {}
        var latestValue = latest[field]
        var lastSegment = segments[segments.length - 1]
        if (latestValue === null || latestValue === undefined
                || !Number.isFinite(Number(latestValue))) return
        context.fillStyle = color
        context.beginPath()
        context.arc(
            lastSegment[lastSegment.length - 2],
            lastSegment[lastSegment.length - 1],
            root.theme.performancePointRadius, 0, Math.PI * 2
        )
        context.fill()
    }
}
