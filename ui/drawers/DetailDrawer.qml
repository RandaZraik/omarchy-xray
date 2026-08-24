import QtQuick
import QtQuick.Controls as QQC
import qs.Ui
import "../controls"
import "../views" as Views
import "../Format.js" as Format
import "../DetailDomains.js" as DetailDomains

DrawerSurface {
    id: root

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

    function accentForDomain(value) {
        if (value === DetailDomains.Connections) return theme.networkAccent;
        if (value === DetailDomains.Files || value === DetailDomains.Coverage)
            return theme.storageAccent;
        if (value === DetailDomains.Devices) return theme.deviceAccent;
        if (value === DetailDomains.Runtime) return theme.runtimeAccent;
        if (value === DetailDomains.Explanations) return theme.alertAccent;
        return theme.processAccent;
    }

    accentColor: accentForDomain(domain)

    MouseArea {
        objectName: "xrayDrawerInputBarrier"
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        preventStealing: true
        onClicked: function(mouse) { mouse.accepted = true; }
    }

    Column {
        anchors.fill: parent
        anchors.margins: root.theme.drawerPadding
        spacing: root.theme.gap

        DrawerHeader {
            width: parent.width
            theme: root.theme
            accentColor: root.accentColor
            eyebrow: root.processDomain ? "PROCESS INSPECTOR" : "EVIDENCE DRAWER"
            title: DetailDomains.title(root.domain)
            detail: root.processDomain
                ? processTable.summary.processes + " processes  ·  "
                    + processTable.summary.threads + " threads  ·  "
                    + Format.bytes(processTable.summary.memoryBytes) + " resident"
                : root.rows.length + " of " + root.allRows.length + " records"
            onClosed: root.closed()
        }

        ThemedTextField {
            id: filterField
            theme: root.theme
            accentColor: root.accentColor
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
            color: root.theme.cardBorder
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
                title: String(modelData.title || "")
                subtitle: String(modelData.subtitle || "")
                meta: String(modelData.meta || "")
                idleColor: root.theme.surfaceLow
                hoverColor: root.theme.surfaceHigh
                selectedColor: root.theme.accentSurface
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
