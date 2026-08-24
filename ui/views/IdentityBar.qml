import QtQuick
import QtQuick.Layouts
import "../controls"
import "../Format.js" as Format

Rectangle {
    id: root
    objectName: "xrayIdentityRail"

    required property var theme
    property var appLibrary: null
    property var snapshot: ({})
    property var performanceSamples: []
    property int performanceWindowSeconds: 60
    signal alternativesRequested()
    signal coverageRequested()

    readonly property var target: snapshot.target || ({})
    readonly property var metrics: snapshot.metrics || ({})
    readonly property var rows: snapshot.processes || []
    readonly property var selectedRow: rows.find(function(row) {
        return Number(row.pid) === Number(root.target.ownerPid || 0)
    }) || ({})
    readonly property var coverage: snapshot.coverage || ({})
    readonly property bool coverageFull: coverage.statusCode === "full"
    readonly property string coverageLabel: coverageFull
        ? "FULL" : coverage.statusCode === "limited"
            ? "LIMITED" : String(coverage.status || "").toUpperCase()
    readonly property color coverageColor: coverageFull
        ? theme.runtimeAccent : theme.danger
    readonly property var appIconCandidates: iconCandidates()
    readonly property string appIconLookupKey: appIconCandidates.join("|")
    property string resolvedAppIconKey: ""
    property string resolvedAppIconSource: ""
    readonly property string appIconSource: resolvedAppIconSource

    function normalizedIdentity(value) {
        return String(value || "").toLowerCase()
            .replace(/\.desktop$/, "").replace(/[^a-z0-9]+/g, ".")
            .replace(/^\.+|\.+$/g, "")
    }

    function entryMatchScore(entry, candidates) {
        var identities = [entry.id, entry.name, entry.icon].map(normalizedIdentity)
        var score = 0
        for (var candidateIndex = 0; candidateIndex < candidates.length; candidateIndex++) {
            var candidate = candidates[candidateIndex]
            if (!candidate) continue
            for (var entryIndex = 0; entryIndex < identities.length; entryIndex++) {
                var identity = identities[entryIndex]
                if (!identity) continue
                if (identity === candidate) score = Math.max(score, 100 - candidateIndex)
                else if (candidate.length >= 4 && (
                    identity.endsWith("." + candidate)
                    || candidate.endsWith("." + identity)
                )) score = Math.max(score, 70 - candidateIndex)
            }
        }
        return score
    }

    function iconCandidates() {
        var context = root.snapshot.context || ({})
        var windowData = context.window || ({})
        var command = root.selectedRow.command || []
        var executable = String(root.selectedRow.executable || context.executable || "")
        var commandName = command.length ? String(command[0]).split("/").pop() : ""
        return [
            root.normalizedIdentity(windowData.class),
            root.normalizedIdentity(root.selectedRow.name),
            root.normalizedIdentity(executable.split("/").pop()),
            root.normalizedIdentity(commandName),
            root.target.kind === "application"
                ? root.normalizedIdentity(root.target.value) : ""
        ]
    }

    function resolveAppIcon(candidates) {
        if (!root.appLibrary || typeof root.appLibrary.sortedEntries !== "function"
                || typeof root.appLibrary.iconSource !== "function") return ""
        var rows = root.appLibrary.sortedEntries("") || []
        var winner = null
        var winnerScore = 0
        for (var index = 0; index < rows.length; index++) {
            var entry = rows[index].entry || rows[index]
            var score = root.entryMatchScore(entry, candidates)
            if (score > winnerScore) {
                winner = entry
                winnerScore = score
            }
        }
        return winner && winnerScore > 0
            ? String(root.appLibrary.iconSource(winner.icon || "")) : ""
    }

    function refreshAppIcon(force) {
        var key = root.appIconLookupKey
        if (!force && key === root.resolvedAppIconKey) return
        root.resolvedAppIconKey = key
        root.resolvedAppIconSource = root.resolveAppIcon(root.appIconCandidates)
    }

    onAppIconLookupKeyChanged: refreshAppIcon(false)
    onAppLibraryChanged: refreshAppIcon(true)
    Component.onCompleted: refreshAppIcon(true)

    function fallbackIconKind() {
        var kind = String(root.target.kind || "process")
        if (["service", "container", "window", "port", "file"].indexOf(kind) >= 0)
            return kind
        var name = String(root.selectedRow.name || "").toLowerCase()
        if (/^(ghostty|kitty|foot|alacritty|wezterm|konsole|xterm)$/.test(name))
            return "terminal"
        if (/^(bash|zsh|fish|dash|sh)$/.test(name)) return "shell"
        return kind === "application" ? "application" : "process"
    }

    height: theme.telemetryHeight
    radius: theme.consoleRadius
    color: theme.consoleSurface
    border.color: theme.consoleBorder
    border.width: theme.borderWidth

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: root.theme.pad
        anchors.rightMargin: root.theme.smallGap
        anchors.topMargin: 3
        spacing: 0

        Item {
            Layout.fillHeight: true
            Layout.preferredWidth: root.theme.telemetryTargetWidth
            Layout.minimumWidth: root.theme.telemetryTargetMinimumWidth
            clip: true

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: root.theme.smallGap
                anchors.rightMargin: root.theme.pad
                anchors.topMargin: root.theme.smallGap
                anchors.bottomMargin: root.theme.smallGap
                spacing: root.theme.gap

                Rectangle {
                    id: identityIconFrame
                    width: 32
                    height: 32
                    radius: root.theme.controlRadius
                    color: root.theme.tintedSurface(root.theme.processAccent)
                    border.color: root.theme.processAccent
                    border.width: root.theme.borderWidth

                    Image {
                        id: appIcon
                        anchors.fill: parent
                        anchors.margins: root.theme.smallGap
                        source: root.appIconSource
                        sourceSize.width: width * 2
                        sourceSize.height: height * 2
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        smooth: true
                        visible: source !== "" && status !== Image.Error
                    }

                    PlainText {
                        anchors.centerIn: parent
                        visible: appIcon.status !== Image.Ready
                        text: Format.icon(root.fallbackIconKind())
                        color: root.theme.processAccent
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.sectionFontSize
                        renderType: Text.NativeRendering
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 1

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.theme.smallGap

                        PlainText {
                            text: "SELECTED TARGET"
                            color: root.theme.processAccent
                            font.family: root.theme.dataFont
                            font.pixelSize: root.theme.microFontSize
                            font.bold: true
                            font.letterSpacing: root.theme.utilityTracking
                        }

                        Item { Layout.fillWidth: true }

                        PlainText {
                            visible: (root.target.alternatives || []).length > 1
                            text: (root.target.alternatives || []).length + " MATCHES"
                            color: matchesHover.hovered
                                ? root.theme.text : root.theme.storageAccent
                            font.family: root.theme.dataFont
                            font.pixelSize: root.theme.microFontSize
                            HoverHandler {
                                id: matchesHover
                                cursorShape: Qt.PointingHandCursor
                            }
                            TapHandler {
                                cursorShape: Qt.PointingHandCursor
                                onTapped: root.alternativesRequested()
                            }
                        }
                    }

                    PlainText {
                        Layout.fillWidth: true
                        text: String(root.target.label || root.target.query || "No target selected")
                        color: root.theme.text
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.summaryFontSize
                        font.bold: true
                        elide: Text.ElideMiddle
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.theme.gap

                        PlainText {
                            text: "PID " + String(root.target.ownerPid || "—")
                            color: root.theme.muted
                            font.family: root.theme.dataFont
                            font.pixelSize: root.theme.microFontSize
                        }
                        PlainText {
                            text: "USER " + String(
                                root.selectedRow.user || root.selectedRow.uid || "—"
                            )
                            color: root.theme.muted
                            font.family: root.theme.dataFont
                            font.pixelSize: root.theme.microFontSize
                        }
                        Row {
                            visible: root.coverageLabel !== ""
                            spacing: root.theme.smallGap

                            Rectangle {
                                width: 6
                                height: 6
                                radius: root.theme.pillRadius
                                anchors.verticalCenter: parent.verticalCenter
                                color: root.coverageColor
                            }
                            PlainText {
                                text: root.coverageLabel
                                color: coverageHover.hovered
                                    ? root.theme.text : root.coverageColor
                                font.family: root.theme.dataFont
                                font.pixelSize: root.theme.microFontSize
                                font.bold: true
                            }
                            HoverHandler {
                                id: coverageHover
                                cursorShape: Qt.PointingHandCursor
                            }
                            TapHandler {
                                cursorShape: Qt.PointingHandCursor
                                onTapped: root.coverageRequested()
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillHeight: true
            Layout.topMargin: root.theme.smallGap
            Layout.bottomMargin: root.theme.smallGap
            width: root.theme.dividerWidth
            color: root.theme.consoleBorder
        }

        Repeater {
            model: [
                {"label": "CPU", "value": Format.percent(root.metrics.cpuPercent), "detail": root.metrics.cpuStatus === "baseline" ? "baseline" : "process share", "accent": root.theme.cpuAccent},
                {"label": "MEM", "value": Format.bytes(root.metrics.memoryBytes), "detail": String(root.metrics.threads || 0) + " threads", "accent": root.theme.memoryAccent},
                {"label": "DISK I/O", "value": root.metrics.ioAvailable === false ? "—" : Format.rate(Number(root.metrics.readBytesPerSecond || 0) + Number(root.metrics.writeBytesPerSecond || 0)), "detail": "read + write", "accent": root.theme.storageAccent},
                {"label": "GPU", "value": Format.percent(root.metrics.gpuPercent), "detail": ((root.snapshot.devices || {}).gpu || []).length + " clients", "accent": root.theme.deviceAccent},
                {"label": "UPTIME", "value": Format.duration(root.metrics.uptimeSeconds), "detail": root.snapshot.samplingPaused ? "paused" : "live", "accent": root.theme.runtimeAccent}
            ]
            delegate: Item {
                required property int index
                required property var modelData
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: root.theme.telemetryMetricWidth
                Layout.minimumWidth: root.theme.telemetryMetricMinimumWidth

                Rectangle {
                    visible: parent.index > 0
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.topMargin: root.theme.smallGap
                    anchors.bottomMargin: root.theme.smallGap
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

        Rectangle {
            Layout.fillHeight: true
            Layout.topMargin: root.theme.smallGap
            Layout.bottomMargin: root.theme.smallGap
            width: root.theme.dividerWidth
            color: root.theme.consoleBorder
        }

        TelemetryTrace {
            Layout.fillHeight: true
            Layout.preferredWidth: root.theme.telemetryTraceWidth
            Layout.minimumWidth: root.theme.telemetryTraceMinimumWidth
            Layout.topMargin: root.theme.smallGap
            Layout.bottomMargin: root.theme.smallGap
            theme: root.theme
            samples: root.performanceSamples
            windowSeconds: root.performanceWindowSeconds
        }
    }
}
