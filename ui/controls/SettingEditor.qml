import QtQuick
import qs.Ui

Rectangle {
    id: root

    required property var theme
    property var settingData: ({})
    property var value
    signal valueEdited(var value)

    width: parent ? parent.width : 0
    height: editorContent.implicitHeight + theme.pad * 2
    radius: theme.controlRadius
    color: theme.surfaceLow
    border.color: theme.cardBorder
    border.width: theme.borderWidth

    Column {
        id: editorContent
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: root.theme.pad
        spacing: root.theme.smallGap

        Column {
            width: parent.width
            spacing: root.theme.smallGap
            visible: root.settingData.type === "choice"

            PlainText {
                width: parent.width
                text: root.settingData.label || ""
                color: root.theme.text
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.labelFontSize
                font.bold: true
            }
            PlainText {
                width: parent.width
                text: root.settingData.description || ""
                color: root.theme.muted
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.captionFontSize
                wrapMode: Text.WordWrap
            }
            Dropdown {
                width: parent.width
                showLabel: false
                options: (root.settingData.options || []).map(function(option) {
                    return {"value": String(option.value), "label": option.label};
                })
                value: String(root.value)
                onChanged: function(value) { root.valueEdited(Number(value)); }
            }
        }

        Toggle {
            width: parent.width
            visible: root.settingData.type === "boolean"
            label: root.settingData.label || ""
            description: root.settingData.description || ""
            checked: root.value === true
            onClicked: root.valueEdited(!checked)
        }
    }
}
