import QtQuick
import QtQuick.Layouts
import qs.Ui
import "../controls"

Rectangle {
    id: root

    property var theme
    property var draft: ({})
    property var schema: []
    property var defaults: ({})
    signal applied(var values)
    signal closed()

    function openWith(values) {
        draft = Object.assign({}, values || {});
    }

    function updateDraft(key, value) {
        var next = Object.assign({}, draft);
        next[key] = value;
        draft = next;
    }

    color: theme.panel
    border.color: theme.border
    border.width: theme.borderWidth

    Column {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 18

        Row {
            width: parent.width
            height: 35
            PlainText { width: parent.width - closeButton.width; text: "X-Ray settings"; color: root.theme.text; font.family: root.theme.bodyFont; font.pixelSize: root.theme.sectionFontSize; font.bold: true }
            IconButton { id: closeButton; iconName: "close"; onClicked: root.closed() }
        }

        PlainText { width: parent.width; text: "Live updates"; color: root.theme.accent; font.family: root.theme.dataFont; font.pixelSize: root.theme.captionFontSize; font.letterSpacing: root.theme.taglineTracking }

        Repeater {
            model: root.schema
            delegate: SettingEditor {
                required property var modelData
                width: parent.width
                theme: root.theme
                settingData: modelData
                value: root.draft[modelData.key] === undefined
                    ? root.defaults[modelData.key]
                    : root.draft[modelData.key]
                onValueEdited: function(value) { root.updateDraft(modelData.key, value); }
            }
        }

        Item { width: 1; height: 1 }

        RowLayout {
            width: parent.width
            spacing: 8
            Button {
                text: "Restore defaults"
                bordered: true
                focusable: true
                onClicked: root.draft = Object.assign({}, root.defaults)
            }
            Item { Layout.fillWidth: true }
            Button {
                text: "Apply settings"
                bordered: true
                selected: true
                focusable: true
                onClicked: root.applied(root.draft)
            }
        }
    }
}
