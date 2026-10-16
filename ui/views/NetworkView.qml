import QtQuick
import QtQuick.Controls as QQC
import qs.Ui
import "../controls"
import "../domains/NetworkRows.js" as NetworkRows
import "../domains/ResourceRows.js" as ResourceRows
import "../Format.js" as Format
import "../DetailDomains.js" as DetailDomains

Item {
    id: root
    objectName: "xrayNetworkView"
    required property var theme
    property var snapshot: ({})
    property bool liveEnabled: true
    property bool busy: false
    property string tab: "map"
    property string search: ""
    property string scope: ""
    property string protocol: ""
    property string sort: "process"
    property bool toolsVisible: false
    property bool limitsVisible: false
    property bool limitsExpanded: false
    property bool flowExpanded: false
    property bool captureErrorExpanded: false
    property string selectedId: ""
    property string captureInterface: ""
    property string ownerPid: ""
    property string focusedFlowId: ""
    readonly property var network: snapshot.network || ({})
    readonly property var capture: network.capture || ({})
    readonly property var selected: (network.flows || []).find(function(row) { return String(row.id) === root.selectedId }) || null
    readonly property var selectedOwner: selected ? (selected.owners || []).find(function(owner) { return String(owner.pid) === root.ownerPid }) || null : null
    onSelectedChanged: {
        var owners = selected ? selected.owners || [] : []
        if (!owners.some(function(owner) { return String(owner.pid) === root.ownerPid }))
            ownerPid = owners.length ? String(owners[0].pid) : ""
    }
    readonly property var mapRows: visible && tab === "map" ? NetworkRows.flowRows(network, search, scope, protocol, sort, false) : []
    readonly property var socketRows: visible && tab === "sockets" ? DetailDomains.filterRows(ResourceRows.connections(snapshot), search) : []
    readonly property var eventRows: visible && tab === "history" ? (network.events || []).filter(function(row) { return [row.address, row.port, row.protocol, NetworkRows.owners(row), row.kind].join(" ").toLowerCase().indexOf(root.search.trim().toLowerCase()) >= 0 }) : []
    onMapRowsChanged: {
        if (!flowList || !flowList.activeFocus || !focusedFlowId) return
        var key = focusedFlowId
        Qt.callLater(function() {
            if (!flowList.activeFocus || root.tab !== "map") return
            var index = root.mapRows.findIndex(function(row) { return String(row.id) === key })
            if (index < 0) return
            flowList.currentIndex = index
            flowList.positionViewAtIndex(index, ListView.Contain)
            flowList.forceLayout()
            var delegate = flowList.itemAtIndex(index)
            if (delegate && delegate.item) delegate.item.forceActiveFocus()
        })
    }
    signal configured(var options)
    signal ownerSelected(var owner)
    signal copyRequested(string text)

    function choose(id) {
        if (selectedId !== id) flowExpanded = false
        selectedId = id
        toolsVisible = false
        limitsVisible = false
    }
    onVisibleChanged: if (!visible) {
        search = ""
        selectedId = ""
        toolsVisible = false
        limitsVisible = false
        limitsExpanded = false
        flowExpanded = false
        captureErrorExpanded = false
    }
    onCaptureChanged: {
        var available = capture.interfaces || []
        if (available.indexOf(captureInterface) < 0)
            captureInterface = available.indexOf(capture.interface) >= 0 ? capture.interface : ""
    }

    Component {
        id: flowDelegate
        NetworkFlowRow {
            width: parent.width
            theme: root.theme
            row: parent.modelData
            selected: String(row.id) === root.selectedId
            onChosen: function(flowId) { root.choose(flowId); }
            onFocused: function(flowId) {
                root.focusedFlowId = flowId
                flowList.currentIndex = parent.index
                flowList.positionViewAtIndex(parent.index, ListView.Contain)
            }
        }
    }
    Component {
        id: socketDelegate
        ConnectionDrawerRow {
            width: parent.width
            theme: root.theme
            row: parent.modelData
        }
    }
    Component {
        id: eventDelegate
        CompactRow {
            width: parent.width
            height: root.theme.networkFlowRowHeight
            property var event: parent.modelData
            theme: root.theme
            title: (event.kind === "opened" ? "First seen  " : "No longer open  ") + Format.addressPort(event.address, event.port)
            subtitle: NetworkRows.owners(event) + " · " + event.protocol
            meta: NetworkRows.timestamp(event.at)
            interactive: (root.network.flows || []).some(function(row) { return row.id === event.flowId })
            accentColor: root.theme.networkAccent
            onClicked: root.choose(event.flowId)
        }
    }

    Column {
        anchors.fill: parent
        spacing: root.theme.gap

        Item {
            width: parent.width
            height: Math.max(tabs.implicitHeight, optionsButton.implicitHeight)
            Row {
                id: tabs
                spacing: root.theme.smallGap
                Repeater {
                    model: [{"id": "map", "label": "Map"}, {"id": "sockets", "label": "Sockets"}, {"id": "history", "label": "History"}]
                    delegate: ActionButton {
                        required property var modelData
                        objectName: "xrayNetworkTab_" + modelData.id
                        theme: root.theme
                        text: modelData.label
                        variant: root.tab === modelData.id ? "primary" : "neutral"
                        accentColor: root.theme.networkAccent
                        onClicked: { root.tab = modelData.id; root.selectedId = ""; }
                    }
                }
            }
            ActionButton {
                id: optionsButton
                anchors.right: parent.right
                objectName: "xrayNetworkMeasurementOptions"
                theme: root.theme
                text: "Options" + (root.toolsVisible ? " −" : " +")
                onClicked: { root.toolsVisible = !root.toolsVisible; root.limitsVisible = false; root.selectedId = ""; }
            }
        }

        EvidenceSummaryStrip {
            objectName: "xrayNetworkTotals"
            width: parent.width
            height: implicitHeight
            theme: root.theme
            accentColor: root.theme.networkAccent
            stats: NetworkRows.stats(root.network)
        }

        Row {
            width: parent.width
            spacing: root.theme.gap
            ReadingText {
                theme: root.theme
                width: parent.width - limitsButton.width - parent.spacing
                font.pixelSize: root.theme.labelFontSize
                color: root.theme.text
                text: (!root.liveEnabled ? "Recorded" : root.snapshot.samplingPaused ? "Paused" : "Live")
                    + (root.network.mode === "packets" ? " · Packet rates on " + root.capture.interface : " · TCP rates")
            }
            ActionButton {
                id: limitsButton
                objectName: "xrayNetworkLimits"
                theme: root.theme
                text: "Data status " + (root.limitsVisible ? "−" : "+")
                onClicked: { root.limitsVisible = !root.limitsVisible; root.toolsVisible = false; root.selectedId = ""; }
            }
        }

        PerformancePlot {
            visible: root.tab === "map" && !root.toolsVisible && !root.limitsVisible
            width: parent.width
            height: root.theme.networkPlotHeight
            theme: root.theme
            samples: visible ? (root.network.samples || []).map(function(sample) { return Object.assign({"capturedAt": Number(sample.at) * 1000}, sample) }) : []
            primaryField: "sentRate"
            secondaryField: "receivedRate"
            primaryColor: root.theme.networkAccent
            secondaryColor: root.theme.deviceAccent
            minimumPrimaryScale: 1
            secondaryFromZero: true
            sharedScale: true
            windowSeconds: Number((root.snapshot.settings || {}).historySeconds || 300)
        }

        Flickable {
            id: optionsPanel
            visible: root.toolsVisible
            width: parent.width
            height: Math.min(optionsContent.implicitHeight, root.height * 0.45)
            contentHeight: optionsContent.implicitHeight
            clip: true
            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }
            Column {
                id: optionsContent
                width: parent.width - root.theme.drawerListInset
                spacing: root.theme.gap
                EvidenceFacts {
                    objectName: "xrayNetworkCaptureSummary"
                    width: parent.width
                    theme: root.theme
                    rows: [{"label": "Packet capture", "value": NetworkRows.captureStatus(root.capture),
                        "tone": root.capture.active ? "network" : root.capture.error ? "storage" : ""}]
                }
                Row {
                    width: parent.width
                    spacing: root.theme.gap
                    Dropdown {
                        objectName: "xrayNetworkInterface"
                        width: parent.width * 0.45
                        showLabel: false
                        enabled: root.liveEnabled && !root.capture.active && !root.capture.starting && !root.busy && !root.snapshot.samplingPaused
                        options: [{"label": "Choose interface…", "value": ""}].concat((root.capture.interfaces || []).map(function(name) { return {"label": (root.capture.interfaceLabels || {})[name] || name, "value": name} }))
                        value: root.captureInterface
                        onChanged: function(value) { root.captureInterface = value; }
                    }
                    ActionButton {
                        objectName: "xrayNetworkCaptureToggle"
                        theme: root.theme
                        enabled: root.liveEnabled && !root.busy && !root.capture.starting && (root.capture.active || !!root.captureInterface) && !root.snapshot.samplingPaused
                        text: root.capture.starting ? "Starting…" : root.capture.active ? "Stop capture" : root.capture.error ? "Retry capture" : "Start capture"
                        accentColor: root.theme.networkAccent
                        variant: root.capture.active ? "primary" : "neutral"
                        onClicked: root.configured({"capture": !root.capture.active, "interface": root.captureInterface})
                    }
                }
                ReadingText {
                    width: parent.width
                    theme: root.theme
                    font.pixelSize: root.theme.labelFontSize
                    text: "Includes UDP. Switching capture on or off resets totals."
                }
                ActionButton {
                    visible: !!root.capture.error
                    objectName: "xrayNetworkCaptureErrorDetails"
                    theme: root.theme
                    text: root.captureErrorExpanded ? "Hide error details" : "Error details"
                    onClicked: root.captureErrorExpanded = !root.captureErrorExpanded
                }
                ReadingText {
                    objectName: "xrayNetworkCaptureStatus"
                    visible: !!root.capture.error && root.captureErrorExpanded
                    width: parent.width
                    theme: root.theme
                    color: root.theme.storageAccent
                    font.pixelSize: root.theme.labelFontSize
                    text: root.capture.error || ""
                }
                Rectangle {
                    width: parent.width
                    height: root.theme.dividerWidth
                    color: root.theme.cardBorder
                }
                Toggle {
                    objectName: "xrayNetworkNamesToggle"
                    width: parent.width
                    label: "Look up names · " + (checked ? "On" : "Off")
                    description: "Uses system DNS. Names may not identify the website."
                    checked: root.network.resolveNames === true
                    enabled: root.liveEnabled && !root.busy && !root.snapshot.samplingPaused
                    foreground: root.theme.text
                    accent: root.theme.networkAccent
                    fontFamily: root.theme.bodyFont
                    titleSize: root.theme.labelFontSize
                    descriptionSize: root.theme.labelFontSize
                    radius: root.theme.controlRadius
                    onClicked: root.configured({"resolveNames": !checked})
                }
            }
        }

        Flickable {
            visible: root.limitsVisible
            width: parent.width
            height: Math.min(coverageContent.implicitHeight, root.height * 0.4)
            contentHeight: coverageContent.implicitHeight
            clip: true
            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }
            Column {
                id: coverageContent
                width: parent.width - root.theme.drawerListInset
                spacing: root.theme.gap
                EvidenceFacts {
                    objectName: "xrayNetworkCoverageFacts"
                    width: parent.width
                    theme: root.theme
                    rows: NetworkRows.coverageFacts(root.network)
                }
                ActionButton {
                    objectName: "xrayNetworkCoverageDetails"
                    theme: root.theme
                    text: root.limitsExpanded ? "Hide technical details" : "Technical details"
                    onClicked: root.limitsExpanded = !root.limitsExpanded
                }
                EvidenceFacts {
                    objectName: "xrayNetworkCoverageTechnical"
                    visible: root.limitsExpanded
                    width: parent.width
                    theme: root.theme
                    rows: root.limitsExpanded ? NetworkRows.coverageDetails(root.network) : []
                }
            }
        }

        ThemedTextField {
            objectName: "xrayNetworkSearch"
            width: parent.width
            theme: root.theme
            accentColor: root.theme.networkAccent
            placeholderText: "Search destination, process, PID, port, or protocol…"
            sourceText: root.search
            onTextEdited: root.search = text
        }

        Row {
            visible: root.tab === "map"
            width: parent.width
            spacing: root.theme.gap
            Dropdown {
                objectName: "xrayNetworkScope"
                width: parent.width * 0.36
                showLabel: false
                options: [{"value": "", "label": "All destinations"}].concat(["internet", "local", "loopback", "multicast"].map(function(scope) { return {"value": scope, "label": NetworkRows.scopes[scope]} }))
                value: root.scope
                onChanged: function(value) { root.scope = value; }
            }
            Dropdown {
                objectName: "xrayNetworkProtocol"
                width: parent.width * 0.22
                showLabel: false
                options: [{"value": "", "label": "TCP + UDP"}, {"value": "TCP", "label": "TCP"}, {"value": "UDP", "label": "UDP"}]
                value: root.protocol
                onChanged: function(value) { root.protocol = value; }
            }
            ActionButton {
                objectName: "xrayNetworkSort"
                theme: root.theme
                text: root.sort === "process" ? "By process ↓" : "Recent first ↓"
                onClicked: root.sort = root.sort === "process" ? "recent" : "process"
            }
        }

        ListView {
            id: flowList
            objectName: "xrayNetworkList"
            width: parent.width
            height: Math.max(0, parent.height - y - (details.visible ? details.height + parent.spacing : 0))
            model: root.tab === "map" ? root.mapRows : root.tab === "sockets" ? root.socketRows : root.eventRows
            clip: true
            reuseItems: true
            boundsBehavior: Flickable.StopAtBounds
            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }
            delegate: Loader {
                required property var modelData
                required property int index
                width: flowList.width - root.theme.drawerListInset
                height: item ? item.implicitHeight : root.theme.networkFlowRowHeight
                sourceComponent: root.tab === "map" ? flowDelegate : root.tab === "sockets" ? socketDelegate : eventDelegate
            }
            ReadingText {
                visible: flowList.count === 0
                anchors.centerIn: parent
                width: parent.width - root.theme.pad * 2
                theme: root.theme
                color: root.theme.muted
                horizontalAlignment: Text.AlignHCenter
                text: root.search || root.scope || root.protocol ? "No connections match these filters."
                    : !root.snapshot.network ? "This report has no network history. Open Sockets for its recorded connections."
                    : root.tab === "history" ? "Connection changes will appear here while you inspect this app."
                    : "No remote connections observed. Use the app to generate traffic, or open Sockets to see listeners."
            }
        }

        Rectangle {
            id: details
            objectName: "xrayNetworkEvidence"
            visible: root.selected !== null
            width: parent.width
            height: Math.min(detailsContent.implicitHeight + root.theme.pad * 2, root.height * 0.4,
                Math.max(0, root.height - flowList.y - root.theme.networkFlowRowHeight - parent.spacing))
            color: root.theme.surfaceLow
            radius: root.theme.controlRadius
            border.color: root.theme.cardBorder
            border.width: root.theme.borderWidth
            Flickable {
                anchors.fill: parent
                anchors.margins: root.theme.pad
                contentHeight: detailsContent.implicitHeight
                clip: true
                QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }
            Column {
                id: detailsContent
                width: parent.width - root.theme.drawerListInset
                spacing: root.theme.gap
                Flow {
                    width: parent.width
                    spacing: root.theme.smallGap
                    ActionButton {
                        theme: root.theme
                        text: "Close details"
                        onClicked: root.selectedId = ""
                    }
                    ActionButton {
                        objectName: "xrayNetworkCopy"
                        theme: root.theme
                        text: "Copy endpoint"
                        onClicked: if (root.selected) root.copyRequested(NetworkRows.endpoint(root.selected))
                    }
                    Dropdown {
                        visible: root.selected && (root.selected.owners || []).length > 1
                        width: Math.max(100, parent.width * 0.3)
                        showLabel: false
                        options: (root.selected ? root.selected.owners || [] : []).map(function(owner) { return {"label": owner.name + " · " + owner.pid, "value": String(owner.pid)} })
                        value: root.ownerPid
                        onChanged: function(value) { root.ownerPid = value; }
                    }
                    ActionButton {
                        objectName: "xrayNetworkInspectOwner"
                        theme: root.theme
                        text: "Inspect " + root.ownerPid
                        enabled: root.liveEnabled && root.selectedOwner !== null && NetworkRows.canInspect(root.selectedOwner, root.snapshot.processes)
                        onClicked: root.ownerSelected(root.selectedOwner)
                    }
                }
                EvidenceFacts {
                    width: parent.width
                    theme: root.theme
                    rows: root.selected ? NetworkRows.flowFacts(root.selected) : []
                }
                ActionButton {
                    objectName: "xrayNetworkFlowDetails"
                    theme: root.theme
                    text: root.flowExpanded ? "Less detail" : "More detail"
                    onClicked: root.flowExpanded = !root.flowExpanded
                }
                EvidenceFacts {
                    visible: root.flowExpanded
                    width: parent.width
                    theme: root.theme
                    rows: root.flowExpanded && root.selected ? NetworkRows.flowDetails(root.network, root.selected) : []
                }
            }
            }
        }
    }
}
