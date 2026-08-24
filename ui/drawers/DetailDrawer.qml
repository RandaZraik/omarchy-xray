import QtQuick
import QtQuick.Controls as QQC
import qs.Ui
import "../controls"
import "../views" as Views
import "../Format.js" as Format
import "../DetailDomains.js" as DetailDomains

Rectangle {
    id: root

    property var theme
    property var snapshot: ({})
    property string domain: ""
    property string filterText: ""
    property bool selectionEnabled: true
    readonly property bool processDomain: domain === DetailDomains.Processes
    signal closed()
    signal processSelected(int pid)
    readonly property var allRows: visible ? DetailDomains.rows(domain, snapshot) : []
    readonly property var rows: processDomain ? processTable.rows : allRows.filter(
        function(row) {
            var needle = root.filterText.toLowerCase();
            return !needle || (String(row.title || "") + " "
                + String(row.subtitle || "") + " "
                + String(row.meta || "")).toLowerCase().indexOf(needle) >= 0;
        }
    )

    color: processDomain ? theme.inspectorCanvas : theme.panel
    border.color: processDomain ? theme.inspectorAccentBorder : theme.border
    border.width: theme.borderWidth

    MouseArea {
        objectName: "xrayDrawerInputBarrier"
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        preventStealing: true
        onClicked: function(mouse) { mouse.accepted = true; }
    }

    Column {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        Item {
            width: parent.width
            height: root.processDomain ? 46 : 34

            Column {
                anchors.left: parent.left
                anchors.right: closeButton.left
                anchors.rightMargin: root.theme.pad
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2

                PlainText {
                    text: DetailDomains.title(root.domain)
                    color: root.theme.text
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.sectionFontSize
                    font.bold: true
                }

                PlainText {
                    text: root.processDomain
                        ? processTable.summary.processes + " processes  ·  "
                            + processTable.summary.threads + " threads  ·  "
                            + Format.bytes(processTable.summary.memoryBytes)
                            + " resident"
                        : root.rows.length + " of " + root.allRows.length + " records"
                    color: root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.captionFontSize
                    elide: Text.ElideRight
                }
            }

            IconButton {
                id: closeButton
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                iconName: "close"
                tooltipText: "Close drawer"
                onClicked: root.closed()
            }
        }

        TextField {
            width: parent.width
            placeholderText: root.processDomain
                ? "Filter process, command, user, or PID…"
                : "Filter this list…"
            text: root.filterText
            onTextChanged: root.filterText = text
        }

        Rectangle {
            width: parent.width
            height: root.theme.dividerWidth
            color: root.processDomain ? root.theme.cardBorder : root.theme.border
            opacity: root.theme.subtleDividerOpacity
        }

        Views.ProcessEvidenceTable {
            id: processTable
            visible: root.processDomain
            width: parent.width
            height: parent.height - y
            theme: root.theme
            snapshot: root.processDomain ? root.snapshot : ({})
            filterText: root.processDomain ? root.filterText : ""
            selectionEnabled: root.selectionEnabled
            onProcessSelected: function(pid) { root.processSelected(pid); }
        }

        ListView {
            visible: !root.processDomain
            width: parent.width
            height: parent.height - y
            model: root.processDomain ? [] : root.rows
            reuseItems: true
            clip: true
            spacing: 4
            boundsBehavior: Flickable.StopAtBounds

            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

            delegate: CompactRow {
                required property var modelData
                width: ListView.view.width - 8
                height: 60
                theme: root.theme
                title: modelData.title
                subtitle: modelData.subtitle
                meta: modelData.meta
                idleColor: root.theme.quietSurface
                titleElide: Text.ElideMiddle
                horizontalPadding: 10
                textSpacing: 3
                interactive: root.selectionEnabled
                    && DetailDomains.selectable(root.domain)
                    && !!modelData.pid
                onClicked: root.processSelected(Number(modelData.pid))
            }
        }
    }
}
