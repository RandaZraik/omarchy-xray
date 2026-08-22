import QtQuick
import QtQuick.Layouts
import "../controls"
import "../Format.js" as Format

Card {
    id: root
    objectName: "xrayPerformanceCard"

    property var snapshot: ({})
    readonly property var metrics: snapshot.metrics || {}
    property var samples: []
    property var memorySamples: []
    property int windowSeconds: 60
    title: "Performance · last " + windowSeconds + " seconds"
    countText: "CPU / MEMORY"

    onSamplesChanged: chart.requestPaint()
    onMemorySamplesChanged: chart.requestPaint()

    body: Item {
        anchors.fill: parent

        Canvas {
            id: chart
            anchors.left: parent.left
            anchors.right: legend.left
            anchors.rightMargin: 14
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            antialiasing: true

            onPaint: {
                var context = getContext("2d");
                context.reset();
                context.lineWidth = 1;
                context.strokeStyle = root.theme.grid;
                for (var grid = 1; grid < 4; grid++) {
                    var gridY = grid * height / 4;
                    context.beginPath();
                    context.moveTo(0, gridY);
                    context.lineTo(width, gridY);
                    context.stroke();
                }
                var cpuMax = Math.max.apply(Math, root.samples.concat([100]));
                root.drawSeries(context, root.samples, cpuMax * 1.08, root.theme.trace, 2.1);
                var memoryMax = Math.max.apply(Math, root.memorySamples.concat([1]));
                root.drawSeries(context, root.memorySamples, memoryMax * 1.12, root.theme.secondaryTrace, 1.55);
            }
        }

        Column {
            id: legend
            width: 92
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 16

            Metric { width: parent.width; theme: root.theme; accentColor: root.theme.cpuAccent; value: Format.percent(root.metrics.cpuPercent); label: "CPU NOW" }
            Metric { width: parent.width; theme: root.theme; accentColor: root.theme.memoryAccent; value: Format.bytes(root.metrics.memoryBytes); label: "MEMORY" }
            Metric { width: parent.width; theme: root.theme; accentColor: root.theme.storageAccent; value: root.metrics.ioAvailable === false ? "—" : Format.rate(Number(root.metrics.readBytesPerSecond || 0) + Number(root.metrics.writeBytesPerSecond || 0)); label: "DISK I/O" }
        }
    }

    function drawSeries(context, values, maximum, color, width) {
        if (!values.length) return;
        var step = chart.width / Math.max(1, values.length - 1);
        context.strokeStyle = color;
        context.lineWidth = width;
        context.beginPath();
        for (var index = 0; index < values.length; index++) {
            var x = index * step;
            var y = chart.height - Math.min(maximum, Number(values[index] || 0)) / Math.max(1, maximum) * (chart.height - 8) - 4;
            if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
        }
        context.stroke();
    }
}
