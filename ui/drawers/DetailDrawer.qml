import QtQuick
import QtQuick.Controls as QQC
import QtQml.Models
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
    property var collapsedSections: ({})
    signal closed()
    signal processSelected(int pid)
    readonly property var allRows: visible ? DetailDomains.rows(domain, snapshot) : []
    readonly property var rows: processDomain
        ? processTable.rows : DetailDomains.filterRows(allRows, filterText)
    readonly property var preparedPresentation: processDomain
        ? ({"sectioned": false, "rows": [], "sections": [], "flatRows": []})
        : DetailDomains.preparePresentation(domain, rows)
    readonly property var displayRows: processDomain
        ? [] : preparedPresentation.flatRows || []
    readonly property int visibleRowCount: processDomain ? 0 : evidenceModel.count
    readonly property var summaryStats: DetailDomains.summary(domain, snapshot, allRows)

    function sectionKey(id) {
        return root.domain + ":" + String(id || "section")
    }

    function toggleSection(id) {
        var next = Object.assign({}, root.collapsedSections)
        var key = root.sectionKey(id)
        next[key] = next[key] !== true
        root.collapsedSections = next
        root.applySectionVisibility(id)
    }

    function sectionCollapsed(id) {
        return filterText.trim() === ""
            && collapsedSections[sectionKey(id)] === true
    }

    function preparedSection(id) {
        var sections = preparedPresentation.sections || []
        for (var index = 0; index < sections.length; index++) {
            if (String(sections[index].id) === String(id)) return sections[index]
        }
        return null
    }

    function applySectionVisibility(id) {
        var section = preparedSection(id)
        if (!section || !section.childCount
                || evidenceModel.items.count !== displayRows.length) return
        var groups = ["visible"]
        if (sectionCollapsed(id))
            evidenceModel.items.removeGroups(
                section.childStart, section.childCount, groups
            )
        else
            evidenceModel.items.addGroups(
                section.childStart, section.childCount, groups
            )
    }

    function syncSectionVisibility() {
        if (processDomain || evidenceModel.items.count !== displayRows.length) {
            if (!processDomain) sectionSync.restart()
            return
        }
        ;(preparedPresentation.sections || []).forEach(function(section) {
            root.applySectionVisibility(section.id)
        })
    }

    function sectionForRow(sourceIndex) {
        var sections = preparedPresentation.sections || []
        for (var index = 0; index < sections.length; index++) {
            var section = sections[index]
            if (sourceIndex >= section.childStart
                    && sourceIndex < section.childStart + section.childCount)
                return section
        }
        return null
    }

    function rowAccent(row) {
        return root.theme.toneColor(DetailDomains.rowTone(root.domain, row))
    }

    function headerDetail() {
        return DetailDomains.detail(root.domain, root.snapshot, root.allRows,
            root.rows, root.filterText.trim() !== "", processTable.summary)
    }

    accentColor: theme.toneColor(DetailDomains.tone(domain))

    Component {
        id: sectionRowComponent
        DrawerSectionHeader {
            theme: parent.themeValue
            accentColor: parent.rowAccentValue
            iconName: String(parent.rowData.icon || "device")
            title: String(parent.rowData.title || "")
            count: Number(parent.rowData.count || 0)
            countLabel: String(parent.rowData.countLabel || "")
            collapsed: root.sectionCollapsed(parent.rowData.sectionId)
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

    DelegateModel {
        id: evidenceModel
        model: root.processDomain ? [] : root.displayRows
        filterOnGroup: "visible"
        groups: DelegateModelGroup {
            name: "visible"
            includeByDefault: true
        }
        delegate: Loader {
            id: rowLoader
            required property var modelData
            readonly property var rowData: modelData
            readonly property var themeValue: root.theme
            readonly property int sourceIndex: DelegateModel.itemsIndex
            readonly property var sourceSection: root.sectionForRow(sourceIndex)
            readonly property color rowAccentValue: root.rowAccent(modelData)
            readonly property bool rowSelectable: root.selectionEnabled
                && DetailDomains.selectable(root.domain) && !!modelData.pid
            readonly property bool firstInSection: sourceSection
                && sourceIndex === sourceSection.childStart
            readonly property bool lastInSection: sourceSection
                && sourceIndex === sourceSection.childStart + sourceSection.childCount - 1
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
    }

    Timer {
        id: sectionSync
        interval: 0
        repeat: false
        onTriggered: root.syncSectionVisibility()
    }

    onPreparedPresentationChanged: sectionSync.restart()
    onFilterTextChanged: sectionSync.restart()

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
            onTextChanged: root.filterText = text
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
            model: root.processDomain ? [] : evidenceModel
            reuseItems: true
            clip: true
            spacing: 0
            boundsBehavior: Flickable.StopAtBounds

            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

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
