import QtQuick
import QtQuick.Layouts
import qs.Ui
import "../controls"

DrawerSurface {
    id: root

    accentColor: theme.memoryAccent

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

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.theme.drawerPadding
        spacing: root.theme.gap

        DrawerHeader {
            Layout.fillWidth: true
            theme: root.theme
            accentColor: root.accentColor
            eyebrow: "X-RAY SETTINGS"
            title: "Live inspection"
            detail: "Choose how X-Ray samples and captures local evidence."
            onClosed: root.closed()
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: root.theme.cardRadius
            color: root.theme.surfaceMid
            border.color: root.theme.cardBorder
            border.width: root.theme.borderWidth

            Column {
                anchors.fill: parent
                anchors.margins: root.theme.pad
                spacing: root.theme.gap

                PlainText {
                    width: parent.width
                    text: "SAMPLING & PRIVACY"
                    color: root.theme.accent
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                    font.bold: true
                    font.letterSpacing: root.theme.utilityTracking
                }

                Rectangle {
                    width: parent.width
                    height: root.theme.dividerWidth
                    color: root.theme.cardBorder
                }

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
                        onValueEdited: function(value) {
                            root.updateDraft(modelData.key, value);
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: root.theme.smallGap

            ActionButton {
                theme: root.theme
                accentColor: root.accentColor
                text: "Restore defaults"
                foreground: root.theme.muted
                onClicked: root.draft = Object.assign({}, root.defaults)
            }
            Item { Layout.fillWidth: true }
            ActionButton {
                theme: root.theme
                accentColor: root.accentColor
                variant: "primary"
                text: "Apply settings"
                onClicked: root.applied(root.draft)
            }
        }
    }
}
