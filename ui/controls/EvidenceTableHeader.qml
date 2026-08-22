import QtQuick

Row {
    id: root

    required property var theme
    property var columns: []
    height: 24

    Repeater {
        model: root.columns
        delegate: PlainText {
            required property var modelData
            width: root.width * Number(modelData.width || 0)
            anchors.verticalCenter: parent.verticalCenter
            text: String(modelData.text || "")
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            elide: Text.ElideRight
        }
    }
}
