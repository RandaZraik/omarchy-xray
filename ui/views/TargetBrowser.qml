import QtQuick
import QtQuick.Controls as QQC
import qs.Ui as Ui
import "../controls"
import "../Format.js" as Format
import "../TargetSearch.js" as TargetSearch

Rectangle {
    id: root
    objectName: "xrayTargetBrowser"

    required property var theme
    property var catalog: ({})
    property var target: ({})
    property string currentQuery: ""
    property bool interactionEnabled: true
    property bool catalogLoading: false
    property bool closable: true
    property string activeFilter: "all"
    property int currentIndex: -1
    property string keyboardQuery: ""
    property string stableTargetKey: ""
    property string stableTargetQuery: ""
    property string contextualOwnerQuery: ""
    property var contextualOwners: []
    property var collapsedGroups: ({})
    readonly property var catalogEntries: TargetSearch.entries(catalog)
    readonly property string queryText: searchField.text
    readonly property bool searching: queryText.trim().length > 0
    readonly property var searchMatches: TargetSearch.matches(
        queryText, catalogEntries, Math.max(1, targetCount + shortcutCount), activeFilter
    )
    readonly property var ownerMatches: shouldShowOwners() ? contextualOwners : []
    readonly property var rows: buildRows()
    readonly property int targetCount: TargetSearch.targetCount(catalogEntries)
    readonly property int shortcutCount: TargetSearch.shortcutCount(catalogEntries)
    readonly property bool catalogLimited: (catalog.limited || []).length > 0

    signal selected(string query)
    signal catalogRequested()
    signal closeRequested()

    radius: theme.radius
    color: theme.browserSurface
    border.color: theme.cardBorder
    border.width: theme.borderWidth
    clip: true

    function normalized(value) {
        return String(value || "").trim().toLowerCase()
    }

    function shouldShowOwners() {
        return searching
            && normalized(queryText) === normalized(contextualOwnerQuery)
            && contextualOwners.length > 1
    }

    function appendSection(result, label, count) {
        if (count > 0)
            result.push({
                "rowType": "section",
                "label": label,
                "count": count,
                "collapsed": isGroupCollapsed(label)
            })
    }

    function appendTargets(result, values) {
        values.forEach(function(value) {
            result.push(Object.assign({"rowType": "target"}, value))
        })
    }

    function appendGrouped(result, values) {
        var groups = {}
        var groupOrder = []
        values.forEach(function(value) {
            var label = TargetSearch.groupLabel(value.kind)
            if (!groups[label]) {
                groups[label] = []
                groupOrder.push(label)
            }
            groups[label].push(value)
        })
        groupOrder.forEach(function(label) {
            appendSection(result, label, groups[label].length)
            if (!isGroupCollapsed(label))
                appendTargets(result, groups[label])
        })
    }

    function buildRows() {
        var result = []
        if (searching) {
            appendSection(result, "MATCHING OWNERS", ownerMatches.length)
            if (!isGroupCollapsed("MATCHING OWNERS"))
                appendTargets(result, ownerMatches)
            var ownerQueries = ownerMatches.map(function(value) { return value.query })
            var matches = searchMatches.filter(function(value) {
                return ownerQueries.indexOf(value.query) < 0
            })
            appendSection(result, "SEARCH RESULTS", matches.length)
            if (!isGroupCollapsed("SEARCH RESULTS"))
                appendTargets(result, matches)
            return result
        }
        appendGrouped(result, TargetSearch.browse(catalogEntries, activeFilter))
        return result
    }

    function isGroupCollapsed(label) {
        return collapsedGroups[String(label || "")] === true
    }

    function toggleGroup(label) {
        var key = String(label || "")
        if (!key) return
        var next = Object.assign({}, collapsedGroups)
        next[key] = !isGroupCollapsed(key)
        collapsedGroups = next
    }

    function selectableIndex(start, delta) {
        if (!rows.length) return -1
        var index = start
        for (var attempts = 0; attempts < rows.length; attempts++) {
            index = (index + delta + rows.length) % rows.length
            if (rows[index].rowType === "target") return index
        }
        return -1
    }

    function moveSelection(delta) {
        currentIndex = selectableIndex(currentIndex, delta)
        if (currentIndex >= 0) resultList.positionViewAtIndex(currentIndex, ListView.Contain)
    }

    function resetBrowsePosition() {
        Qt.callLater(function() { resultList.positionViewAtBeginning(); })
    }

    function acceptCurrent() {
        if (currentIndex < 0 || currentIndex >= rows.length
                || rows[currentIndex].rowType !== "target") return false
        choose(rows[currentIndex])
        return true
    }

    function choose(row) {
        if (!row || !row.query) return
        keyboardQuery = row.query
        selected(row.query)
    }

    function focusSearch(selectAll) {
        catalogRequested()
        searchField.forceActiveFocus()
        if (selectAll) searchField.selectAll()
    }

    function synchronizeQuery(query) {
        keyboardQuery = String(query || "")
        searchField.text = keyboardQuery
    }

    function isInspected(row) {
        if (!row || row.rowType !== "target") return false
        if (row.selected === true) return true
        return normalized(row.query) === normalized(stableTargetQuery)
    }

    function synchronizeTarget() {
        var value = target || {}
        var inspectionId = Number(value.inspectionId || 0)
        var key = inspectionId > 0
            ? "inspection:" + inspectionId
            : [value.kind, value.value, value.ownerPid].join(":")
        if (!key || key === stableTargetKey) return
        stableTargetKey = key
        stableTargetQuery = String(value.query || currentQuery)
        if (normalized(queryText) === normalized(stableTargetQuery)
                && (value.alternatives || []).length > 1) {
            contextualOwnerQuery = queryText
            contextualOwners = TargetSearch.ownerMatches(value)
        }
    }

    function resetKeyboardSelection() {
        var remembered = keyboardQuery
        var rememberedIndex = rows.findIndex(function(row) {
            return row.rowType === "target" && row.query === remembered
        })
        currentIndex = rememberedIndex >= 0 ? rememberedIndex : selectableIndex(-1, 1)
    }

    onRowsChanged: resetKeyboardSelection()
    onActiveFilterChanged: resetBrowsePosition()
    onTargetChanged: synchronizeTarget()
    onVisibleChanged: if (visible) catalogRequested()
    Component.onCompleted: {
        synchronizeTarget()
        if (visible) catalogRequested()
    }

    Column {
        anchors.fill: parent
        anchors.margins: root.theme.targetBrowserContentPadding
        spacing: root.theme.smallGap

        Item {
            width: parent.width
            height: root.theme.targetBrowserHeaderHeight

            Column {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1
                PlainText {
                    text: "TARGETS"
                    color: root.theme.sectionText
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.captionFontSize
                    font.bold: true
                    font.letterSpacing: root.theme.labelTracking
                }
                Row {
                    spacing: root.theme.smallGap

                    PlainText {
                        text: root.catalogLoading
                            ? "READING SYSTEM…"
                            : root.targetCount + " TARGETS"
                        color: root.theme.muted
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
                        font.letterSpacing: root.theme.utilityTracking
                    }
                    PlainText {
                        visible: !root.catalogLoading && root.catalogLimited
                        text: "LIMITED"
                        color: root.theme.alertAccent
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
                        font.bold: true
                        font.letterSpacing: root.theme.utilityTracking
                    }
                }
            }

            Ui.PanelActionButton {
                visible: root.closable
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                iconText: Format.icon("close")
                tooltipText: "Hide target browser"
                foreground: root.theme.muted
                hoverColor: root.theme.text
                fontFamily: root.theme.dataFont
                fontSize: root.theme.captionFontSize
                size: root.theme.targetBrowserCloseSize
                onClicked: root.closeRequested()
            }
        }

        Item {
            width: parent.width
            height: root.theme.targetBrowserSearchHeight

            Ui.TextField {
                id: searchField
                objectName: "xrayTargetSearchField"
                anchors.fill: parent
                enabled: root.interactionEnabled
                foreground: root.theme.text
                accent: root.theme.accent
                placeholderTextColor: root.theme.muted
                selectionTint: root.theme.selected
                font.pixelSize: root.theme.bodyFontSize
                leftPadding: searchIcon.implicitWidth + root.theme.pad
                rightPadding: keyboardHint.implicitWidth + root.theme.pad
                placeholderText: "App, PID, :port, service…"
                background: Rectangle {
                    radius: root.theme.radius
                    color: searchField.activeFocus
                        ? root.theme.controlFocusSurface : root.theme.previewSurface
                    border.color: searchField.activeFocus
                        ? root.theme.controlFocusBorder : root.theme.cardBorder
                    border.width: root.theme.borderWidth
                }
                onTextEdited: {
                    root.keyboardQuery = ""
                    if (root.normalized(text)
                            !== root.normalized(root.contextualOwnerQuery)) {
                        if (root.contextualOwnerQuery || root.contextualOwners.length) {
                            root.contextualOwnerQuery = ""
                            root.contextualOwners = []
                        }
                    }
                    root.resetBrowsePosition()
                    root.catalogRequested()
                }
                onAccepted: if (!root.acceptCurrent() && text.trim()) root.selected(text)
                Keys.onDownPressed: function(event) {
                    root.moveSelection(1)
                    event.accepted = true
                }
                Keys.onUpPressed: function(event) {
                    root.moveSelection(-1)
                    event.accepted = true
                }
            }
            PlainText {
                id: searchIcon
                anchors.left: parent.left
                anchors.leftMargin: root.theme.smallGap
                anchors.verticalCenter: parent.verticalCenter
                text: Format.icon("search")
                color: searchField.activeFocus
                    ? root.theme.sectionText : root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.captionFontSize
            }
            PlainText {
                id: keyboardHint
                anchors.right: parent.right
                anchors.rightMargin: root.theme.smallGap
                anchors.verticalCenter: parent.verticalCenter
                text: "CTRL K"
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.microFontSize
            }
        }

        Row {
            width: parent.width
            height: root.theme.targetBrowserFilterHeight
            spacing: root.theme.smallGap

            Repeater {
                model: TargetSearch.Filters
                delegate: Item {
                    required property var modelData
                    width: (parent.width - parent.spacing * (TargetSearch.Filters.length - 1))
                        / TargetSearch.Filters.length
                    height: parent.height

                    Rectangle {
                        anchors.fill: parent
                        radius: root.theme.radius
                        color: filterHover.hovered
                            ? root.theme.controlHoverSurface : root.theme.transparent
                    }
                    PlainText {
                        anchors.centerIn: parent
                        text: modelData.label
                        color: root.activeFilter === modelData.id
                            ? root.theme.text : root.theme.muted
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
                        font.bold: root.activeFilter === modelData.id
                    }
                    Rectangle {
                        visible: root.activeFilter === modelData.id
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: root.theme.targetBrowserTabIndicatorHeight
                        color: root.theme.accent
                    }
                    HoverHandler { id: filterHover }
                    TapHandler { onTapped: root.activeFilter = modelData.id }
                }
            }
        }

        Rectangle {
            width: parent.width
            height: root.theme.dividerWidth
            color: root.theme.border
            opacity: root.theme.subtleDividerOpacity
        }

        ListView {
            id: resultList
            objectName: "xrayTargetResults"
            width: parent.width
            height: parent.height - y
            model: root.rows
            reuseItems: true
            clip: true
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds
            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

            delegate: Loader {
                id: resultDelegate
                required property int index
                required property var modelData
                readonly property int rowIndex: index
                width: ListView.view.width - root.theme.smallGap
                height: modelData.rowType === "section"
                    ? root.theme.targetBrowserSectionHeight
                    : root.theme.targetBrowserRowHeight
                sourceComponent: modelData.rowType === "section"
                    ? sectionDelegate : targetDelegate
            }

            Component {
                id: sectionDelegate

                Item {
                    id: sectionHeader
                    readonly property var rowData: parent.modelData
                    anchors.fill: parent

                    Rectangle {
                        anchors.fill: parent
                        radius: root.theme.radius
                        color: sectionHover.hovered
                            ? root.theme.controlHoverSurface : root.theme.transparent
                    }

                    PlainText {
                        id: sectionChevron
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: sectionHeader.rowData.collapsed ? "›" : "⌄"
                        color: root.theme.muted
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.captionFontSize
                    }

                    PlainText {
                        anchors.left: sectionChevron.right
                        anchors.leftMargin: root.theme.smallGap
                        anchors.verticalCenter: parent.verticalCenter
                        text: sectionHeader.rowData.label
                        color: root.theme.sectionText
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
                        font.bold: true
                        font.letterSpacing: root.theme.utilityTracking
                    }
                    PlainText {
                        anchors.right: parent.right
                        anchors.rightMargin: root.theme.smallGap
                        anchors.verticalCenter: parent.verticalCenter
                        text: sectionHeader.rowData.count
                        color: root.theme.muted
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
                    }

                    HoverHandler { id: sectionHover }
                    TapHandler {
                        onTapped: root.toggleGroup(sectionHeader.rowData.label)
                    }
                }
            }

            Component {
                id: targetDelegate

                Item {
                    id: targetItem
                    readonly property var rowData: parent.modelData
                    readonly property int rowIndex: parent.rowIndex
                    anchors.fill: parent

                    CompactRow {
                        anchors.fill: parent
                        theme: root.theme
                        title: targetItem.rowData.title || "Target"
                        subtitle: targetItem.rowData.subtitle
                            || targetItem.rowData.query || ""
                        meta: ""
                        selected: targetItem.rowIndex === root.currentIndex
                            && searchField.activeFocus
                        selectedColor: root.theme.controlActiveSurface
                        hoverColor: root.theme.controlHoverSurface
                        idleColor: root.theme.transparent
                        horizontalPadding: root.theme.pad
                        textSpacing: 2
                        onClicked: root.choose(targetItem.rowData)
                    }

                    Rectangle {
                        visible: root.isInspected(targetItem.rowData)
                        width: root.theme.targetBrowserBeamWidth
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.left: parent.left
                        color: root.theme.accent
                    }
                }
            }

            PlainText {
                visible: root.rows.length === 0
                anchors.top: parent.top
                anchors.topMargin: root.theme.pad
                width: parent.width
                text: root.searching
                    ? "No catalog match. Press Enter to inspect the exact query."
                    : root.catalogLoading ? "Reading running targets…" : "No targets in this group."
                color: root.theme.muted
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.bodyFontSize
                wrapMode: Text.WordWrap
            }
        }
    }
}
