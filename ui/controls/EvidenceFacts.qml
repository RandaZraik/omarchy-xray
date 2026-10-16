import QtQuick

Column {
    id: root
    required property var theme
    property var rows: []
    spacing: theme.gap

    Repeater {
        model: root.rows
        delegate: Row {
            required property var modelData
            width: root.width
            spacing: root.theme.gap

            ReadingText {
                theme: root.theme
                width: Math.min(root.theme.evidenceFactLabelWidth, parent.width * 0.28)
                text: String(parent.modelData.label || "")
                font.pixelSize: root.theme.labelFontSize
                color: root.theme.muted
            }
            ReadingText {
                theme: root.theme
                width: parent.width - x
                text: String(parent.modelData.value || "—")
                font.pixelSize: root.theme.labelFontSize
                color: parent.modelData.tone ? root.theme.toneColor(parent.modelData.tone) : root.theme.text
            }
        }
    }
}
