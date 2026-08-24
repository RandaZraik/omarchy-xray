import QtQuick
import QtQuick.Controls as QQC
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

    radius: theme.consoleRadius
    color: theme.consoleSurface
    border.color: theme.consoleBorder
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
                    text: "TARGET CATALOG"
                    color: root.theme.text
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.labelFontSize
                    font.bold: true
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

            IconButton {
                visible: root.closable
                theme: root.theme
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: root.theme.targetBrowserCloseSize
                height: root.theme.targetBrowserCloseSize
                iconName: "close"
                tooltipText: "Hide target browser"
                onClicked: root.closeRequested()
            }
        }

        Item {
            width: parent.width
            height: root.theme.targetBrowserSearchHeight

            ThemedTextField {
                id: searchField
                theme: root.theme
                objectName: "xrayTargetSearchField"
                anchors.fill: parent
                enabled: root.interactionEnabled
                placeholderTextColor: root.theme.muted
                font.pixelSize: root.theme.bodyFontSize
                leftPadding: root.theme.pad + searchAffordance.width
                    + root.theme.smallGap
                rightPadding: root.theme.pad + keyboardHint.width
                    + root.theme.smallGap
                placeholderText: "App, PID, :port, service…"
                idleSurface: root.theme.previewSurface
                focusSurface: root.theme.controlFocusSurface
                focusBorder: root.theme.controlFocusBorder
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
            Item {
                id: searchAffordance
                anchors.left: parent.left
                anchors.leftMargin: root.theme.pad
                anchors.verticalCenter: parent.verticalCenter
                width: 16
                height: 20

                PlainText {
                    anchors.centerIn: parent
                    text: Format.icon("search")
                    color: searchField.activeFocus
                        ? root.theme.sectionText : root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.bodyFontSize
                    renderType: Text.NativeRendering
                }
            }
            Rectangle {
                id: keyboardHint
                anchors.right: parent.right
                anchors.rightMargin: root.theme.pad
                anchors.verticalCenter: parent.verticalCenter
                width: keyboardHintText.implicitWidth + root.theme.gap
                height: 20
                radius: root.theme.controlRadius
                color: root.theme.surfaceLow
                border.color: searchField.activeFocus
                    ? root.theme.controlFocusBorder : root.theme.cardBorder
                border.width: root.theme.borderWidth

                PlainText {
                    id: keyboardHintText
                    anchors.centerIn: parent
                    text: "CTRL K"
                    color: searchField.activeFocus
                        ? root.theme.text : root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                    font.bold: true
                    font.letterSpacing: root.theme.utilityTracking * 0.4
                }
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
                        radius: 0
                        color: filterHover.hovered
                            ? root.theme.controlHoverSurface : root.theme.transparent
                    }
                    PlainText {
                        anchors.centerIn: parent
                        text: modelData.label
                        color: root.activeFilter === modelData.id
                            ? root.theme.accent : root.theme.muted
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
                        font.bold: root.activeFilter === modelData.id
                    }
                    Rectangle {
                        visible: root.activeFilter === modelData.id
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 2
                        color: root.theme.accent
                    }
                    HoverHandler {
                        id: filterHover
                        cursorShape: Qt.PointingHandCursor
                    }
                    TapHandler {
                        cursorShape: Qt.PointingHandCursor
                        onTapped: root.activeFilter = modelData.id
                    }
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
                        radius: root.theme.controlRadius
                        color: sectionHover.hovered
                            ? root.theme.controlHoverSurface : root.theme.transparent
                    }

                    PlainText {
                        id: sectionChevron
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: sectionHeader.rowData.collapsed ? "+" : "−"
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

                    HoverHandler {
                        id: sectionHover
                        cursorShape: Qt.PointingHandCursor
                    }
                    TapHandler {
                        cursorShape: Qt.PointingHandCursor
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
                        id: targetRow
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.leftMargin: root.theme.targetBrowserChildIndent
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
                        anchors.left: targetRow.left
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
