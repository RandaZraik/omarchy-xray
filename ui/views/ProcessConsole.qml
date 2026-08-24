import QtQuick
import QtQuick.Controls as QQC
import "../controls"
import "../Format.js" as Format
import "../ProcessEvidence.js" as ProcessEvidence
import "../DetailDomains.js" as DetailDomains

Card {
    id: root
    objectName: "xrayProcessCard"

    property var snapshot: ({})
    property string sortKey: "tree"
    property bool descending: false
    property bool emptyAreaHovered: false
    readonly property var sourceRows: snapshot.processes || []
    readonly property var rows: ProcessEvidence.sort(sourceRows, sortKey, descending)
    readonly property int selectedPid: Number((snapshot.target || {}).ownerPid || 0)
    readonly property var columns: [
        {"key": "tree", "text": "PROGRAM / ST", "width": 0.19},
        {"key": "command", "text": "COMMAND", "width": 0.305},
        {"key": "pid", "text": "PID", "width": 0.09, "right": true},
        {"key": "user", "text": "USER", "width": 0.09},
        {"key": "threads", "text": "THR", "width": 0.065, "right": true},
        {"key": "cpu", "text": "CPU", "width": 0.075, "right": true},
        {"key": "memory", "text": "MEM", "width": 0.105, "right": true},
        {"key": "io", "text": "I/O", "width": 0.08, "right": true}
    ]

    signal processSelected(int pid)
    signal detailsRequested()

    title: "PROCESS TABLE"
    eyebrow: sourceRows.length + " proc / "
        + ProcessEvidence.summary(sourceRows).threads + " thr"
    accentColor: theme.processAccent
    detailsCount: DetailDomains.count(DetailDomains.Processes, snapshot)
    interactive: true
    bodyInteractive: false
    externalHover: emptyAreaHovered
    onClicked: detailsRequested()

    function chooseSort(key) {
        key = String(key || "tree")
        if (sortKey === key) {
            if (key !== "tree") descending = !descending
            return
        }
        sortKey = key
        descending = ["cpu", "memory", "io", "threads"].indexOf(key) >= 0
    }

    function stateColor(row) {
        var code = String((row || {}).state || "?").charAt(0)
        return code === "Z" || code === "X" ? theme.danger : theme.muted
    }

    function columnWidth(key, availableWidth) {
        for (var index = 0; index < columns.length; index++)
            if (columns[index].key === key)
                return availableWidth * Number(columns[index].width || 0)
        return 0
    }

    body: Item {
        anchors.fill: parent

        Rectangle {
            id: commandLine
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: root.theme.consoleCommandHeight
            color: root.theme.consoleSurface

            Rectangle {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: root.theme.telemetryRailWidth
                color: root.accentColor
            }

            PlainText {
                id: prompt
                anchors.left: parent.left
                anchors.leftMargin: root.theme.pad
                anchors.verticalCenter: parent.verticalCenter
                text: "$"
                color: root.accentColor
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.bodyFontSize
                font.bold: true
            }

            PlainText {
                anchors.left: prompt.right
                anchors.right: processIdentity.left
                anchors.leftMargin: root.theme.smallGap
                anchors.rightMargin: root.theme.gap
                anchors.verticalCenter: parent.verticalCenter
                text: {
                    var selected = root.sourceRows.find(function(row) {
                        return Number(row.pid) === root.selectedPid
                    })
                    return selected ? ProcessEvidence.command(selected) : "no command selected"
                }
                color: root.theme.text
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.captionFontSize
                elide: Text.ElideMiddle
            }

            PlainText {
                id: processIdentity
                anchors.right: parent.right
                anchors.rightMargin: root.theme.pad
                anchors.verticalCenter: parent.verticalCenter
                text: root.selectedPid ? "PID " + root.selectedPid : "NO PID"
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.microFontSize
            }
        }

        EvidenceTableHeader {
            id: tableHeader
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: commandLine.bottom
            theme: root.theme
            columns: root.columns
            sortKey: root.sortKey
            descending: root.descending
            sortable: true
            headerHeight: root.theme.consoleTableHeaderHeight
            backgroundColor: root.theme.surfaceLow
            activeColor: root.accentColor
            accentColor: root.accentColor
            onColumnActivated: function(key) { root.chooseSort(key) }
        }

        ListView {
            id: processList
            objectName: "xrayProcessEvidenceRows"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: tableHeader.bottom
            anchors.bottom: parent.bottom
            model: root.rows
            reuseItems: true
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

            delegate: Item {
                id: row
                required property var modelData
                required property int index
                width: ListView.view.width
                height: root.theme.consoleProcessRowHeight
                readonly property bool selected: Number(modelData.pid) === root.selectedPid
                readonly property int depth: root.sortKey === "tree"
                    ? Math.min(root.theme.processEvidenceMaximumDepth,
                        Number(modelData.depth || 0)) : 0
                readonly property int indent: depth * root.theme.processEvidenceIndent

                Rectangle {
                    anchors.fill: parent
                    color: row.selected
                        ? root.theme.inspectorSelectedSurface
                        : rowHover.hovered ? root.theme.controlHoverSurface
                            : root.theme.transparent
                }

                Rectangle {
                    visible: row.selected
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: root.theme.telemetryRailWidth
                    color: root.accentColor
                }

                Row {
                    anchors.fill: parent

                    Item {
                        width: root.columnWidth("tree", parent.width)
                        height: parent.height

                        Rectangle {
                            visible: row.depth > 0
                            x: root.theme.smallGap + row.indent
                            y: 0
                            width: 1
                            height: parent.height / 2
                            color: root.accentColor
                            opacity: 0.55
                        }
                        Rectangle {
                            visible: row.depth > 0
                            x: root.theme.smallGap + row.indent
                            y: parent.height / 2
                            width: root.theme.processEvidenceBranchWidth
                            height: 1
                            color: root.accentColor
                            opacity: 0.55
                        }
                        PlainText {
                            anchors.left: parent.left
                            anchors.leftMargin: root.theme.smallGap + row.indent
                                + (row.depth ? root.theme.processEvidenceBranchWidth : 0)
                            anchors.right: state.left
                            anchors.rightMargin: 4
                            anchors.verticalCenter: parent.verticalCenter
                            text: String(row.modelData.name || "process")
                            color: row.selected ? root.theme.text : root.theme.sectionText
                            font.family: root.theme.dataFont
                            font.pixelSize: root.theme.bodyFontSize
                            font.bold: row.selected
                            elide: Text.ElideRight
                        }
                        PlainText {
                            id: state
                            anchors.right: parent.right
                            anchors.rightMargin: root.theme.smallGap
                            anchors.verticalCenter: parent.verticalCenter
                            text: String(row.modelData.state || "?").charAt(0)
                            color: root.stateColor(row.modelData)
                            font.family: root.theme.dataFont
                            font.pixelSize: root.theme.microFontSize
                        }
                    }

                    Item {
                        width: root.columnWidth("command", parent.width)
                        height: parent.height
                        PlainText {
                            anchors.fill: parent
                            anchors.leftMargin: root.theme.smallGap
                            anchors.rightMargin: root.theme.smallGap
                            text: ProcessEvidence.presentation(row.modelData).command
                            color: root.theme.muted
                            font.family: root.theme.dataFont
                            font.pixelSize: root.theme.captionFontSize
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideMiddle
                        }
                    }

                    Repeater {
                        model: [
                            {"key": "pid", "value": String(row.modelData.pid || "—"), "color": root.theme.text},
                            {"key": "user", "value": ProcessEvidence.user(row.modelData), "color": root.theme.muted, "left": true},
                            {"key": "threads", "value": String(row.modelData.threads || 0), "color": root.theme.text},
                            {"key": "cpu", "value": Format.percent(row.modelData.cpuPercent), "color": Number(row.modelData.cpuPercent || 0) >= 25 ? root.theme.danger : root.theme.cpuAccent},
                            {"key": "memory", "value": Format.bytes(row.modelData.memoryBytes), "color": root.theme.memoryAccent},
                            {"key": "io", "value": row.modelData.readBytesPerSecond === null && row.modelData.writeBytesPerSecond === null ? "—" : Format.rate(Number(row.modelData.readBytesPerSecond || 0) + Number(row.modelData.writeBytesPerSecond || 0)), "color": root.theme.storageAccent}
                        ]
                        delegate: Item {
                            required property var modelData
                            width: root.columnWidth(String(modelData.key), parent.width)
                            height: parent.height
                            PlainText {
                                anchors.fill: parent
                                anchors.leftMargin: root.theme.smallGap
                                anchors.rightMargin: root.theme.smallGap
                                text: parent.modelData.value
                                color: parent.modelData.color
                                font.family: root.theme.dataFont
                                font.pixelSize: root.theme.captionFontSize
                                verticalAlignment: Text.AlignVCenter
                                horizontalAlignment: parent.modelData.left
                                    ? Text.AlignLeft : Text.AlignRight
                                elide: Text.ElideRight
                            }
                        }
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: root.theme.dividerWidth
                    color: root.theme.cardBorder
                    opacity: 0.28
                }

                HoverHandler {
                    id: rowHover
                    cursorShape: Qt.PointingHandCursor
                }
                TapHandler {
                    cursorShape: Qt.PointingHandCursor
                    onTapped: root.processSelected(Number(row.modelData.pid))
                }
            }

            footer: Item {
                width: processList.width
                height: Math.max(0, processList.height
                    - root.rows.length * root.theme.consoleProcessRowHeight)

                HoverHandler {
                    id: emptyAreaHover
                    cursorShape: Qt.PointingHandCursor
                    onHoveredChanged: root.emptyAreaHovered = hovered
                }
                Component.onDestruction: root.emptyAreaHovered = false
                TapHandler {
                    cursorShape: Qt.PointingHandCursor
                    onTapped: root.detailsRequested()
                }
            }
        }
    }
}
