import QtQuick
import QtQuick.Controls as QQC
import "../controls"
import "../Format.js" as Format
import "../ProcessEvidence.js" as ProcessEvidence

Item {
    id: root
    objectName: "xrayProcessEvidenceTable"

    required property var theme
    property var snapshot: ({})
    property string filterText: ""
    property bool selectionEnabled: true
    property string sortKey: "tree"
    property bool descending: false
    readonly property bool expanded: width >= theme.processEvidenceExpandedWidth
    readonly property real contentWidth: Math.max(0, width - theme.smallGap)
    readonly property var filteredRows: ProcessEvidence.filter(
        snapshot.processes || [], filterText
    )
    readonly property var rows: ProcessEvidence.sort(filteredRows, sortKey, descending)
    readonly property var summary: ProcessEvidence.summary(filteredRows)
    readonly property int selectedPid: Number((snapshot.target || {}).ownerPid || 0)
    readonly property var selectedRow: (snapshot.processes || []).find(function(row) {
        return Number(row.pid) === root.selectedPid
    }) || null
    readonly property string selectedCommand: selectedRow
        ? ProcessEvidence.command(selectedRow) : ""
    readonly property var columns: [
        { "key": "process", "sort": "tree", "text": "PROCESS / COMMAND",
          "width": expanded ? 0.40 : 0.47 },
        { "key": "pid", "sort": "pid", "text": "PID",
          "width": expanded ? 0.085 : 0.11, "right": true },
        { "key": "user", "sort": "user", "text": "USER",
          "width": expanded ? 0.095 : 0.13 },
        { "key": "threads", "sort": "threads", "text": expanded ? "THREADS" : "THR",
          "width": expanded ? 0.08 : 0.09, "right": true },
        { "key": "cpu", "sort": "cpu", "text": "CPU",
          "width": expanded ? 0.085 : 0.09, "right": true },
        { "key": "memory", "sort": "memory", "text": "MEMORY",
          "width": expanded ? 0.12 : 0.11, "right": true },
        { "key": "io", "sort": "io", "text": "READ / WRITE",
          "width": expanded ? 0.135 : 0, "right": true }
    ]

    signal processSelected(int pid)

    component ValueCell: Item {
        required property var theme
        required property string value
        property color valueColor: theme.text
        property bool emphasized: false
        property int alignment: Text.AlignRight
        property int leftPadding: theme.smallGap
        property int rightPadding: theme.smallGap
        property int valueFontSize: theme.processEvidenceValueFontSize
        property int textElide: Text.ElideNone

        PlainText {
            anchors.fill: parent
            anchors.leftMargin: parent.leftPadding
            anchors.rightMargin: parent.rightPadding
            text: parent.value
            color: parent.valueColor
            font.family: parent.theme.dataFont
            font.pixelSize: parent.valueFontSize
            font.bold: parent.emphasized
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: parent.alignment
            elide: parent.textElide
        }
    }

    function chooseSort(key) {
        key = String(key || "tree")
        if (key === "program" || key === "process") key = "tree"
        if (sortKey === key) {
            if (key !== "tree") descending = !descending
            return
        }
        sortKey = key
        descending = ["cpu", "memory", "io", "read", "write", "threads"].indexOf(key) >= 0
    }

    function columnWidth(key, availableWidth) {
        for (var index = 0; index < columns.length; index++)
            if (columns[index].key === key)
                return availableWidth * Number(columns[index].width || 0)
        return 0
    }

    function stateColor(row) {
        var code = String((row || {}).state || "?").charAt(0)
        return code === "Z" || code === "X" ? root.theme.danger : root.theme.muted
    }

    function displayCommand(row) {
        var value = ProcessEvidence.presentation(row)
        return value.command + (value.launcher ? "  ·  " + value.launcher : "")
    }

    Item {
        id: selectedStrip
        objectName: "xraySelectedProcessCommand"
        width: root.contentWidth
        height: root.selectedCommand ? Math.max(
            root.theme.processEvidenceCommandHeight,
            selectedCommandText.y + selectedCommandText.implicitHeight
                + root.theme.smallGap
        ) : 0
        visible: height > 0

        Rectangle {
            anchors.fill: parent
            radius: root.theme.cardRadius
            border.color: root.theme.accentBorder
            border.width: root.theme.borderWidth
            color: root.theme.surfaceLow
        }

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: root.theme.telemetryRailWidth
            radius: root.theme.pillRadius
            color: root.theme.inspectorAccent
        }

        Item {
            id: selectedIdentity
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: root.theme.pad
            anchors.rightMargin: root.theme.pad
            anchors.topMargin: root.theme.smallGap
            height: 24

            Row {
                anchors.left: parent.left
                anchors.right: selectedOwner.left
                anchors.rightMargin: root.theme.gap
                anchors.verticalCenter: parent.verticalCenter
                spacing: root.theme.smallGap

                PlainText {
                    width: Math.max(0, parent.width
                        - selectedState.implicitWidth - parent.spacing)
                    text: String((root.selectedRow || {}).name || "Process")
                    color: root.theme.text
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.processEvidencePrimaryFontSize
                    font.bold: true
                    elide: Text.ElideRight
                }

                PlainText {
                    id: selectedState
                    text: "·  " + ProcessEvidence.state(root.selectedRow || {})
                    color: root.stateColor(root.selectedRow || {})
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.processEvidenceBadgeFontSize
                }
            }

            PlainText {
                id: selectedOwner
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: "PID " + root.selectedPid + "  ·  "
                    + ProcessEvidence.user(root.selectedRow || {})
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.processEvidenceSecondaryFontSize
            }
        }

        PlainText {
            id: selectedCommandLabel
            anchors.left: parent.left
            anchors.leftMargin: root.theme.pad
            anchors.top: selectedIdentity.bottom
            anchors.topMargin: root.theme.smallGap
            text: "COMMAND"
            color: root.theme.inspectorAccentText
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            font.bold: true
            font.letterSpacing: root.theme.utilityTracking
        }

        PlainText {
            id: selectedCommandText
            objectName: "xraySelectedProcessCommandText"
            anchors.left: selectedCommandLabel.right
            anchors.right: parent.right
            anchors.top: selectedIdentity.bottom
            anchors.leftMargin: root.theme.pad
            anchors.rightMargin: root.theme.pad
            anchors.topMargin: root.theme.smallGap - 1
            text: root.selectedCommand
            color: root.theme.text
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.processEvidenceSecondaryFontSize
            wrapMode: Text.WrapAnywhere
            maximumLineCount: 2
            elide: Text.ElideRight
        }
    }

    Rectangle {
        x: 0
        y: selectedStrip.visible ? selectedStrip.height + root.theme.gap : 0
        width: root.contentWidth
        height: Math.max(0, parent.height - y)
        radius: root.theme.cardRadius
        color: root.theme.consoleSurface
        border.color: root.theme.cardBorder
        border.width: root.theme.borderWidth
        clip: true

        EvidenceTableHeader {
            id: tableHeader
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: root.theme.borderWidth
            theme: root.theme
            columns: root.columns
            sortKey: root.sortKey
            descending: root.descending
            sortable: true
            signalVisible: true
            headerHeight: root.theme.processEvidenceHeaderHeight
            fontSize: root.theme.processEvidenceHeaderFontSize
            backgroundColor: root.theme.surfaceLow
            activeColor: root.theme.inspectorAccentText
            onColumnActivated: function(key) { root.chooseSort(key); }
        }

        ListView {
            objectName: "xrayProcessEvidenceRows"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: tableHeader.bottom
            anchors.bottom: parent.bottom
            anchors.leftMargin: root.theme.borderWidth
            anchors.rightMargin: root.theme.borderWidth
            anchors.bottomMargin: root.theme.borderWidth
            model: root.rows
            reuseItems: true
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

            delegate: Item {
                id: processRow
                required property var modelData
                width: ListView.view.width
                height: root.theme.processEvidenceRowHeight
                readonly property int depth: root.sortKey === "tree"
                    ? Math.min(root.theme.processEvidenceMaximumDepth,
                        Number(modelData.depth || 0)) : 0
                readonly property int indent: depth * root.theme.processEvidenceIndent
                readonly property bool selected: Number(modelData.pid) === root.selectedPid

                Rectangle {
                    anchors.fill: parent
                    color: processRow.selected
                        ? root.theme.inspectorSelectedSurface
                        : processHover.hovered
                            ? root.theme.controlHoverSurface : root.theme.transparent

                    Behavior on color {
                        ColorAnimation { duration: root.theme.fastMotionDuration }
                    }
                }

                Rectangle {
                    visible: processRow.selected
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: root.theme.telemetryRailWidth
                    color: root.theme.inspectorAccent
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: root.theme.pad
                    anchors.rightMargin: root.theme.pad
                    height: root.theme.dividerWidth
                    color: root.theme.cardBorder
                    opacity: root.theme.subtleDividerOpacity * 0.45
                }

                Row {
                    anchors.fill: parent

                    Item {
                        width: root.columnWidth("process", parent.width)
                        height: parent.height

                        Rectangle {
                            visible: processRow.depth > 0
                            x: root.theme.pad + processRow.indent
                            y: 0
                            width: root.theme.dividerWidth
                            height: parent.height / 2
                            color: root.theme.inspectorAccent
                            opacity: root.theme.connectorOpacity
                        }

                        Rectangle {
                            visible: processRow.depth > 0
                            x: root.theme.pad + processRow.indent
                            y: parent.height / 2
                            width: root.theme.processEvidenceBranchWidth
                            height: root.theme.dividerWidth
                            color: root.theme.inspectorAccent
                            opacity: root.theme.connectorOpacity
                        }

                        Rectangle {
                            visible: processRow.depth > 0
                            x: root.theme.pad + processRow.indent
                                + root.theme.processEvidenceBranchWidth - 2
                            y: parent.height / 2 - 2
                            width: 4
                            height: 4
                            radius: 2
                            color: root.theme.inspectorAccent
                        }

                        Column {
                            anchors.left: parent.left
                            anchors.leftMargin: root.theme.pad + processRow.indent
                                + (processRow.depth > 0
                                    ? root.theme.processEvidenceBranchWidth + 3 : 0)
                            anchors.right: parent.right
                            anchors.rightMargin: root.theme.pad
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 3

                            Row {
                                width: parent.width
                                height: 22
                                spacing: root.theme.smallGap

                                PlainText {
                                    width: Math.max(0, parent.width
                                        - processState.implicitWidth - parent.spacing)
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: String(processRow.modelData.name || "Process")
                                    color: processRow.selected
                                        ? root.theme.inspectorAccentText : root.theme.text
                                    font.family: root.theme.bodyFont
                                    font.pixelSize: root.theme.processEvidencePrimaryFontSize
                                    font.bold: processRow.selected
                                    elide: Text.ElideRight
                                }

                                PlainText {
                                    id: processState
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "·  " + ProcessEvidence.state(processRow.modelData)
                                    color: root.stateColor(processRow.modelData)
                                    font.family: root.theme.dataFont
                                    font.pixelSize: root.theme.processEvidenceBadgeFontSize
                                }
                            }

                            PlainText {
                                width: parent.width
                                text: root.displayCommand(processRow.modelData)
                                color: root.theme.muted
                                font.family: root.theme.dataFont
                                font.pixelSize: root.theme.processEvidenceSecondaryFontSize
                                elide: Text.ElideMiddle
                            }
                        }
                    }

                    ValueCell {
                        width: root.columnWidth("pid", parent.width)
                        height: parent.height
                        theme: root.theme
                        value: String(processRow.modelData.pid || "—")
                        emphasized: processRow.selected
                        leftPadding: root.theme.pad
                    }

                    ValueCell {
                        width: root.columnWidth("user", parent.width)
                        height: parent.height
                        theme: root.theme
                        value: ProcessEvidence.user(processRow.modelData)
                        valueColor: root.theme.muted
                        alignment: Text.AlignLeft
                        leftPadding: root.theme.pad
                        textElide: Text.ElideRight
                    }

                    ValueCell {
                        width: root.columnWidth("threads", parent.width)
                        height: parent.height
                        theme: root.theme
                        value: String(processRow.modelData.threads ?? "—")
                    }

                    ValueCell {
                        width: root.columnWidth("cpu", parent.width)
                        height: parent.height
                        theme: root.theme
                        value: Format.percent(processRow.modelData.cpuPercent)
                        valueColor: Number(processRow.modelData.cpuPercent || 0) >= 25
                            ? root.theme.danger : root.theme.text
                        emphasized: Number(processRow.modelData.cpuPercent || 0) > 0
                    }

                    ValueCell {
                        width: root.columnWidth("memory", parent.width)
                        height: parent.height
                        theme: root.theme
                        value: Format.bytes(processRow.modelData.memoryBytes)
                        leftPadding: root.theme.pad
                    }

                    ValueCell {
                        visible: root.expanded
                        width: root.columnWidth("io", parent.width)
                        height: parent.height
                        theme: root.theme
                        value: Format.rate(processRow.modelData.readBytesPerSecond)
                            + "  /  "
                            + Format.rate(processRow.modelData.writeBytesPerSecond)
                        valueColor: root.theme.muted
                        rightPadding: root.theme.pad
                        valueFontSize: root.theme.processEvidenceSecondaryFontSize
                        textElide: Text.ElideLeft
                    }
                }

                HoverHandler {
                    id: processHover
                    enabled: root.selectionEnabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                }
                TapHandler {
                    enabled: root.selectionEnabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onTapped: root.processSelected(Number(processRow.modelData.pid))
                }
            }
        }
    }
}
