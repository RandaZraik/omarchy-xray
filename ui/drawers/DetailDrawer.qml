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
    readonly property bool performanceDomain: domain === DetailDomains.Performance
    property bool technicalDetails: false
    property var expandedChecks: ({})
    property string focusedPerformanceRow: ""
    readonly property int targetPid: Number((snapshot.target || {}).rootPid || 0)
    onTargetPidChanged: expandedChecks = ({})
    readonly property int performanceCheckCount: ((snapshot.performance || {}).checks || []).length
    property var collapsedSections: ({})
    signal closed()
    signal processSelected(int pid)
    readonly property var rawRows: visible && (!performanceDomain || technicalDetails)
        ? DetailDomains.rows(domain, snapshot) : []
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
    readonly property var summaryStats: visible && !performanceDomain
        ? DetailDomains.summary(domain, snapshot, searchRows) : []
    onDisplayRowsChanged: {
        if (!performanceDomain || !evidenceList || !evidenceList.activeFocus || !focusedPerformanceRow) return
        Qt.callLater(function() {
            if (!evidenceList.activeFocus) return
            var index = root.displayRows.findIndex(function(row) {
                return root.performanceRowKey(row) === root.focusedPerformanceRow
            })
            if (index < 0) return
            evidenceList.currentIndex = index
            evidenceList.positionViewAtIndex(index, ListView.Contain)
            evidenceList.forceLayout()
            var delegate = evidenceList.itemAtIndex(index)
            if (delegate && delegate.item) delegate.item.focusHeader()
        })
    }

    function performanceRowKey(row) {
        return row.rowType === "section" ? "section:" + row.sectionId : row.findingId
    }

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
        technicalDetails = false
        expandedChecks = ({})
        focusedPerformanceRow = ""
    }

    onDomainChanged: {
        filterDelay.stop()
        pendingFilterText = ""
        filterText = ""
        technicalDetails = false
        expandedChecks = ({})
        focusedPerformanceRow = ""
    }

    function toggleSection(id) {
        var next = Object.assign({}, root.collapsedSections)
        var key = DetailDomains.sectionKey(root.domain, id)
        next[key] = next[key] !== true
        root.collapsedSections = next
    }

    function toggleCheck(id) {
        var next = Object.assign({}, expandedChecks)
        next[id] = !next[id]
        expandedChecks = next
    }

    function selectPerformanceTab(details) {
        technicalDetails = details
        applyFilterText("")
    }

    function rowAccent(row) {
        return root.theme.toneColor(DetailDomains.rowTone(root.domain, row))
    }

    function headerDetail() {
        return DetailDomains.detail(root.domain, root.snapshot, root.searchRows,
            root.rows, root.filterText.trim() !== "", processTable.summary)
    }

    accentColor: theme.toneColor(DetailDomains.tone(domain))
    radius: performanceDomain ? 10 : theme.consoleRadius
    border.color: performanceDomain ? theme.cardBorder : theme.consoleBorder

    Component {
        id: performanceSectionComponent
        ReadingButton {
            theme: root.theme
            function focusHeader() { forceActiveFocus(Qt.OtherFocusReason) }
            subtle: true
            height: 44
            text: ({"cpu": "CPU", "memory": "Memory", "io": "Disk & I/O", "coverage": "Availability"})[parent.rowData.sectionId]
                + "  ·  " + parent.rowData.count + (parent.rowData.collapsed ? "  +" : "  −")
            contentItem: ReadingText {
                theme: root.theme
                text: parent.text
                color: root.theme.muted
                font.pixelSize: root.theme.readingMetaFontSize
                font.weight: Font.DemiBold
                verticalAlignment: Text.AlignVCenter
            }
            onClicked: parent.sectionToggled(parent.rowData.sectionId)
            onActiveFocusChanged: if (activeFocus) parent.rowFocused()
        }
    }

    Component {
        id: performanceRowComponent
        PerformanceCheckRow {
            theme: root.theme
            row: parent.rowData
            expanded: root.expandedChecks[row.findingId] === true
            onToggled: root.toggleCheck(row.findingId)
            onFocused: parent.rowFocused()
        }
    }

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
        anchors.margins: root.performanceDomain ? 22 : root.theme.drawerPadding
        spacing: root.performanceDomain ? 16 : root.theme.gap

        Item {
            visible: root.performanceDomain
            width: parent.width
            height: 34
            ReadingText {
                theme: root.theme
                text: "Why is this app slow?"
                font.pixelSize: root.theme.readingHeaderFontSize
                font.weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 44
            }
            ReadingButton {
                theme: root.theme
                subtle: true
                anchors.right: parent.right
                text: "×"
                Accessible.name: "Close performance panel"
                onClicked: root.closed()
            }
        }

        Row {
            visible: root.performanceDomain
            width: parent.width
            spacing: 6
            ReadingButton {
                objectName: "xrayPerformanceOverviewTab"
                theme: root.theme
                text: "Overview"
                checked: !root.technicalDetails
                onClicked: root.selectPerformanceTab(false)
            }
            ReadingButton {
                objectName: "xrayPerformanceDetailsToggle"
                theme: root.theme
                text: "Measurements  ·  " + root.performanceCheckCount
                checked: root.technicalDetails
                onClicked: root.selectPerformanceTab(true)
            }
        }

        DrawerHeader {
            visible: !root.performanceDomain
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
            visible: !root.performanceDomain || root.technicalDetails
            theme: root.theme
            accentColor: root.accentColor
            width: parent.width
            font.family: root.performanceDomain ? root.theme.readingFont : root.theme.dataFont
            font.pixelSize: root.performanceDomain ? root.theme.readingBodyFontSize : root.theme.bodyFontSize
            placeholderText: root.processDomain
                ? "Filter process, command, user, or PID…"
                : root.performanceDomain ? "Search measurements…" : "Filter this list…"
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
            visible: root.summaryStats.length > 0 && !root.performanceDomain
            width: parent.width
            height: visible ? implicitHeight : 0
            theme: root.theme
            stats: root.summaryStats
            accentColor: root.accentColor
        }

        ReadingText {
            visible: root.performanceDomain && root.technicalDetails
            width: parent.width
            theme: root.theme
            text: root.headerDetail() + " · Select a measurement for evidence."
            color: root.theme.muted
            font.pixelSize: root.theme.readingMetaFontSize
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

        Views.PerformanceOverview {
            visible: root.performanceDomain && !root.technicalDetails
            width: parent.width
            height: parent.height - y
            theme: root.theme
            performance: visible ? root.snapshot.performance || ({}) : ({})
        }

        ListView {
            id: evidenceList
            visible: !root.processDomain && (!root.performanceDomain || root.technicalDetails)
            width: parent.width
            height: parent.height - y
            model: visible ? root.displayRows : []
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
                // Pooled delegates can outlive their row during a model reset.
                readonly property bool firstInSection: sourceIndex <= 0
                    || sourceIndex >= root.displayRows.length
                    || root.displayRows[sourceIndex - 1].rowType === "section"
                readonly property bool lastInSection: sourceIndex < 0
                    || sourceIndex >= root.displayRows.length - 1
                    || root.displayRows[sourceIndex + 1].rowType === "section"
                signal sectionToggled(string sectionId)
                signal processChosen(int pid)
                signal rowFocused()

                width: ListView.view.width - root.theme.drawerListInset
                height: item ? item.implicitHeight : root.theme.compactRowHeight
                sourceComponent: {
                    if (modelData.rowType === "section") return root.performanceDomain ? performanceSectionComponent : sectionRowComponent
                    if (root.performanceDomain) return performanceRowComponent
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
                onRowFocused: {
                    if (sourceIndex < 0 || sourceIndex >= root.displayRows.length) return
                    root.focusedPerformanceRow = root.performanceRowKey(rowData)
                    evidenceList.currentIndex = sourceIndex
                    evidenceList.positionViewAtIndex(sourceIndex, ListView.Contain)
                    if (y < evidenceList.contentY) evidenceList.contentY = y
                }
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
