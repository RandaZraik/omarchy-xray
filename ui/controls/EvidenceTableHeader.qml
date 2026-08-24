import QtQuick

Item {
    id: root

    required property var theme
    property var columns: []
    property string sortKey: ""
    property bool descending: false
    property bool sortable: false
    property bool signalVisible: false
    property int headerHeight: theme.evidenceHeaderHeight
    property int fontSize: theme.microFontSize
    property color backgroundColor: theme.surfaceLow
    property color activeColor: theme.sectionText
    property color accentColor: theme.accent
    signal columnActivated(string key)

    function columnKey(column) {
        return String(column.sort || column.key || "");
    }

    function columnActive(column) {
        var key = columnKey(column);
        return sortKey === key
            || (String(column.key || "") === "process" && sortKey === "tree");
    }

    height: headerHeight

    Rectangle {
        anchors.fill: parent
        radius: root.theme.controlRadius
        color: root.backgroundColor
    }

    AccentSignal {
        visible: root.signalVisible
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        theme: root.theme
        accentColor: root.accentColor
    }

    Row {
        anchors.fill: parent

        Repeater {
            model: root.columns
            delegate: Item {
                id: cell
                required property var modelData
                width: root.width * Number(modelData.width || 0)
                height: parent.height
                readonly property bool active: root.columnActive(modelData)

                Rectangle {
                    visible: root.sortable && hover.hovered
                    anchors.fill: parent
                    color: root.theme.controlHoverSurface
                }

                PlainText {
                    anchors.fill: parent
                    text: String(cell.modelData.text || "")
                        + (cell.active && root.columnKey(cell.modelData) !== "tree"
                            ? (root.descending ? "  ↓" : "  ↑") : "")
                    color: cell.active ? root.activeColor : root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.fontSize
                    font.bold: cell.active || !root.sortable
                    font.letterSpacing: root.theme.utilityTracking * 0.55
                    leftPadding: root.theme.smallGap
                    rightPadding: root.theme.smallGap
                    verticalAlignment: Text.AlignVCenter
                    horizontalAlignment: cell.modelData.right
                        ? Text.AlignRight : Text.AlignLeft
                    elide: Text.ElideRight
                }

                HoverHandler {
                    id: hover
                    enabled: root.sortable
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                }
                TapHandler {
                    enabled: root.sortable
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onTapped: root.columnActivated(root.columnKey(cell.modelData))
                }
            }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: root.theme.dividerWidth
        color: root.theme.cardBorder
        opacity: root.theme.subtleDividerOpacity
    }
}
