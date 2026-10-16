import QtQuick
import "../Format.js" as Format
import "../domains/NetworkRows.js" as NetworkRows

Rectangle {
    id: root
    required property var theme
    required property var row
    property bool selected: false
    signal chosen(string flowId)
    signal focused(string flowId)
    onActiveFocusChanged: if (activeFocus) focused(String(row.id))
    implicitHeight: theme.networkFlowRowHeight
    height: implicitHeight
    radius: theme.controlRadius
    color: selected || activeFocus ? theme.tintedSurface(theme.networkAccent) : hover.containsMouse ? theme.controlHoverSurface : theme.transparent
    border.color: activeFocus ? theme.networkAccent : theme.transparent
    border.width: theme.borderWidth
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: row.ownerLabel + " to " + row.endpoint + ", " + NetworkRows.status(row)
    Keys.onReturnPressed: chosen(String(row.id))
    Keys.onSpacePressed: chosen(String(row.id))

    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { root.forceActiveFocus(); root.chosen(String(root.row.id)); }
    }
    Canvas {
        id: links
        x: root.width * root.theme.networkOwnerColumn
        width: root.theme.networkLinkWidth
        height: parent.height
        property var data: root.row
        onDataChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var c = getContext("2d")
            c.clearRect(0, 0, width, height)
            c.strokeStyle = root.row.active ? root.theme.networkAccent : root.theme.muted
            c.lineWidth = 1
            c.globalAlpha = root.row.active ? 0.7 : 0.35
            c.beginPath()
            c.moveTo(4, root.row.firstInGroup ? height / 2 : 0)
            c.lineTo(4, root.row.lastInGroup ? height / 2 : height)
            c.moveTo(4, height / 2)
            c.lineTo(width - 5, height / 2)
            c.lineTo(width - 9, height / 2 - 3)
            c.moveTo(width - 5, height / 2)
            c.lineTo(width - 9, height / 2 + 3)
            c.stroke()
        }
    }
    Column {
        x: root.theme.smallGap
        width: root.width * root.theme.networkOwnerColumn - root.theme.gap
        anchors.verticalCenter: parent.verticalCenter
        spacing: root.theme.smallGap
        PlainText {
            width: parent.width
            text: root.row.firstInGroup ? (root.row.owners || []).map(function(owner) { return owner.name }).join(" + ") : ""
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.labelFontSize
            font.bold: true
            color: root.theme.processAccent
            elide: Text.ElideRight
        }
        PlainText {
            width: parent.width
            text: root.row.firstInGroup ? (root.row.owners || []).map(function(owner) { return String(owner.pid) }).join(", ") : ""
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            color: root.theme.muted
            elide: Text.ElideRight
        }
    }
    Column {
        x: links.x + links.width + root.theme.smallGap
        width: Math.max(0, rates.x - x - root.theme.gap)
        anchors.verticalCenter: parent.verticalCenter
        spacing: root.theme.smallGap
        PlainText {
            width: parent.width
            text: root.row.hostname || root.row.endpoint
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.labelFontSize
            color: root.row.active ? root.theme.text : root.theme.muted
            elide: Text.ElideMiddle
        }
        PlainText {
            width: parent.width
            text: root.row.protocol + " · " + root.row.scopeLabel + " · " + (root.row.active ? root.row.state : "Last seen " + NetworkRows.timestamp(root.row.lastSeen))
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            color: root.theme.muted
            elide: Text.ElideRight
        }
    }
    Column {
        id: rates
        anchors.right: parent.right
        anchors.rightMargin: root.theme.smallGap
        anchors.verticalCenter: parent.verticalCenter
        width: root.theme.networkRateColumnWidth
        spacing: root.theme.smallGap
        PlainText {
            width: parent.width
            text: "↑ " + Format.rate(root.row.sentRate)
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
            color: root.theme.networkAccent
            horizontalAlignment: Text.AlignRight
        }
        PlainText {
            width: parent.width
            text: "↓ " + Format.rate(root.row.receivedRate)
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
            color: root.theme.deviceAccent
            horizontalAlignment: Text.AlignRight
        }
    }
}
