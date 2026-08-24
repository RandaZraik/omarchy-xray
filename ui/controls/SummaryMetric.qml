import QtQuick
import QtQuick.Layouts

Item {
    id: root

    required property var theme
    property string label: ""
    property string value: "—"
    property string detail: ""
    property color accentColor: theme.metricText

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: root.theme.telemetryModulePadding
        anchors.rightMargin: root.theme.telemetryModulePadding
        spacing: 2

        Item { Layout.fillHeight: true }
        PlainText {
            Layout.fillWidth: true
            text: root.label.toUpperCase()
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            font.letterSpacing: root.theme.utilityTracking
            elide: Text.ElideRight
        }
        PlainText {
            Layout.fillWidth: true
            text: root.value
            color: root.accentColor
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.summaryFontSize
            font.bold: true
            elide: Text.ElideRight
        }
        PlainText {
            visible: root.detail !== ""
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? implicitHeight : 0
            text: root.detail
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            elide: Text.ElideRight
        }
        Item { Layout.fillHeight: true }
    }
}
