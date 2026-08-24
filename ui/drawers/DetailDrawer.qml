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
    property string pendingFilterText: ""
    property bool selectionEnabled: true
    readonly property bool processDomain: domain === DetailDomains.Processes
    property var collapsedSections: ({})
    signal closed()
    signal processSelected(int pid)
    readonly property var rawRows: visible ? DetailDomains.rows(domain, snapshot) : []
    readonly property var allRows: rawRows
    readonly property var searchRows: processDomain ? rawRows
        : DetailDomains.presentationSource(domain, rawRows)
    readonly property var rows: processDomain
        ? processTable.rows : DetailDomains.filterRows(searchRows, filterText)
    readonly property var preparedPresentation: processDomain
        ? ({"sectioned": false, "rows": [], "sections": [], "expandedRows": []})
        : DetailDomains.preparePresentationFromSource(domain, rows)
    readonly property var displayRows: processDomain
        ? [] : DetailDomains.presentationRowsFromPrepared(
            domain, preparedPresentation, collapsedSections,
            filterText.trim() !== ""
        )
    readonly property int visibleRowCount: processDomain ? 0 : displayRows.length
    readonly property var summaryStats: DetailDomains.summary(domain, snapshot, searchRows)

    function queueFilterText(value) {
        pendingFilterText = String(value || "")
        filterDelay.restart()
    }

    function applyFilterText(value) {
        filterDelay.stop()
        pendingFilterText = String(value || "")
        if (filterText !== pendingFilterText) filterText = pendingFilterText
    }

    onVisibleChanged: if (!visible) {
        filterDelay.stop()
        pendingFilterText = ""
    }

    onDomainChanged: {
        filterDelay.stop()
        pendingFilterText = ""
        filterText = ""
    }

    function toggleSection(id) {
        var next = Object.assign({}, root.collapsedSections)
        var key = DetailDomains.sectionKey(root.domain, id)
        next[key] = next[key] !== true
        root.collapsedSections = next
    }

    function rowAccent(row) {
        return root.theme.toneColor(DetailDomains.rowTone(root.domain, row))
    }

    function headerDetail() {
        return DetailDomains.detail(root.domain, root.snapshot, root.searchRows,
            root.rows, root.filterText.trim() !== "", processTable.summary)
    }

    accentColor: theme.toneColor(DetailDomains.tone(domain))

    Timer {
        id: filterDelay
        interval: 120
        repeat: false
        onTriggered: root.applyFilterText(root.pendingFilterText)
    }

    Component {
        id: sectionRowComponent
        DrawerSectionHeader {
            theme: parent.themeValue
            accentColor: parent.rowAccentValue
            iconName: String(parent.rowData.icon || "device")
            title: String(parent.rowData.title || "")
            count: Number(parent.rowData.count || 0)
            countLabel: String(parent.rowData.countLabel || "")
            collapsed: parent.rowData.collapsed === true
            onToggled: parent.sectionToggled(parent.rowData.sectionId)
        }
    }

    Component {
        id: connectionRowComponent
        ConnectionDrawerRow {
            theme: parent.themeValue
            row: parent.rowData
            accentColor: parent.rowAccentValue
        }
    }

    Component {
        id: fileRowComponent
        FileDrawerRow {
            theme: parent.themeValue
            row: parent.rowData
            accentColor: parent.rowAccentValue
        }
    }

    Component {
        id: deviceRowComponent
        DeviceDrawerRow {
            theme: parent.themeValue
            row: parent.rowData
            accentColor: parent.rowAccentValue
        }
    }

    Component {
        id: findingRowComponent
        FindingDrawerCard {
            theme: parent.themeValue
            row: parent.rowData
            accentColor: parent.rowAccentValue
        }
    }

    Component {
        id: causeRowComponent
        LaunchDrawerRow {
            theme: parent.themeValue
            row: parent.rowData
            accentColor: parent.rowAccentValue
            first: parent.firstInSection
            last: parent.lastInSection
        }
    }

    Component {
        id: compactRowComponent
        CompactRow {
            theme: parent.themeValue
            title: String(parent.rowData.title || "")
            subtitle: String(parent.rowData.subtitle || "")
            meta: String(parent.rowData.meta || "")
            leadingText: parent.rowData.rowType === "alternative"
                ? Format.icon("process")
                : parent.rowData.rowType === "timeline" ? Format.icon("log")
                    : parent.rowData.rowType === "coverage"
                        ? Format.icon(parent.rowData.available ? "coverage" : "warning")
                        : ""
            leadingBordered: false
            accentColor: parent.rowAccentValue
            selected: parent.rowData.selected === true
            idleColor: theme.transparent
            hoverColor: theme.controlHoverSurface
            selectedColor: theme.accentSurface
            titleElide: Text.ElideMiddle
            horizontalPadding: theme.pad
            textSpacing: 1
            interactive: parent.rowSelectable
            onClicked: parent.processChosen(Number(parent.rowData.pid))
        }
    }

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
            eyebrow: ""
            title: DetailDomains.title(root.domain)
            detail: root.headerDetail()
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
            onTextEdited: root.queueFilterText(text)
            onAccepted: root.applyFilterText(text)
            onEditingFinished: root.applyFilterText(text)
        }

        Rectangle {
            width: parent.width
            height: root.theme.dividerWidth
            color: root.theme.cardBorder
            opacity: root.theme.subtleDividerOpacity
        }

        EvidenceSummaryStrip {
            id: evidenceStats
            visible: root.summaryStats.length > 0
            width: parent.width
            height: visible ? implicitHeight : 0
            theme: root.theme
            stats: root.summaryStats
            accentColor: root.accentColor
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
            id: evidenceList
            visible: !root.processDomain
            width: parent.width
            height: parent.height - y
            model: root.processDomain ? [] : root.displayRows
            reuseItems: true
            clip: true
            spacing: 0
            boundsBehavior: Flickable.StopAtBounds

            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

            delegate: Loader {
                id: rowLoader
                required property var modelData
                required property int index
                readonly property var rowData: modelData
                readonly property var themeValue: root.theme
                readonly property int sourceIndex: index
                readonly property color rowAccentValue: root.rowAccent(modelData)
                readonly property bool rowSelectable: root.selectionEnabled
                    && DetailDomains.selectable(root.domain) && !!modelData.pid
                readonly property bool firstInSection: sourceIndex === 0
                    || root.displayRows[sourceIndex - 1].rowType === "section"
                readonly property bool lastInSection:
                    sourceIndex === root.displayRows.length - 1
                    || root.displayRows[sourceIndex + 1].rowType === "section"
                signal sectionToggled(string sectionId)
                signal processChosen(int pid)

                width: ListView.view.width - root.theme.drawerListInset
                height: item ? item.implicitHeight : root.theme.compactRowHeight
                sourceComponent: {
                    if (modelData.rowType === "section") return sectionRowComponent
                    if (modelData.rowType === "connection") return connectionRowComponent
                    if (modelData.rowType === "fileGroup" || modelData.rowType === "lock")
                        return fileRowComponent
                    if (modelData.rowType === "device") return deviceRowComponent
                    if (modelData.rowType === "finding") return findingRowComponent
                    if (modelData.rowType === "cause") return causeRowComponent
                    return compactRowComponent
                }
                onSectionToggled: function(sectionId) { root.toggleSection(sectionId) }
                onProcessChosen: function(pid) { root.processSelected(pid) }
            }

            PlainText {
                visible: !root.processDomain && root.rows.length === 0
                width: evidenceList.width - root.theme.pad * 2
                anchors.centerIn: parent
                text: root.filterText
                    ? "No records match this filter."
                    : "No " + DetailDomains.title(root.domain).toLowerCase()
                        + " evidence for this target."
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.bodyFontSize
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }

        }
    }
}
