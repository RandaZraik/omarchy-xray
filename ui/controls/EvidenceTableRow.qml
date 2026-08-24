import QtQuick

Item {
    id: root

    required property var theme
    property var cells: []
    height: theme.evidenceRowHeight

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: root.theme.dividerWidth
        color: root.theme.cardBorder
        opacity: root.theme.subtleDividerOpacity
    }

    Row {
        anchors.fill: parent
        Repeater {
            model: root.cells
            delegate: PlainText {
                required property var modelData
                width: root.width * Number(modelData.width || 0)
                anchors.verticalCenter: parent.verticalCenter
                text: String(modelData.text ?? "")
                color: modelData.color || root.theme.text
                font.family: modelData.fontFamily || root.theme.dataFont
                font.pixelSize: modelData.fontSize || root.theme.captionFontSize
                leftPadding: root.theme.smallGap
                rightPadding: root.theme.smallGap
                elide: modelData.elide === undefined ? Text.ElideRight : modelData.elide
            }
        }
    }
}
