import QtQuick
import QtQuick.Controls as QQC
import qs.Ui
import "../controls"
import "../DetailDomains.js" as DetailDomains

Rectangle {
    id: root

    property var theme
    property var snapshot: ({})
    property string domain: ""
    property string filterText: ""
    property bool selectionEnabled: true
    signal closed()
    signal processSelected(int pid)
    readonly property var allRows: visible ? DetailDomains.rows(domain, snapshot) : []
    readonly property var rows: allRows.filter(function(row) {
        var needle = root.filterText.toLowerCase();
        return !needle || (String(row.title || "") + " " + String(row.subtitle || "") + " " + String(row.meta || "")).toLowerCase().indexOf(needle) >= 0;
    })

    color: theme.panel
    border.color: theme.border
    border.width: theme.borderWidth

    Column {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        Row {
            width: parent.width
            height: 34

            Column {
                width: parent.width - closeButton.width
                spacing: 1
                PlainText { text: DetailDomains.title(root.domain); color: root.theme.text; font.family: root.theme.bodyFont; font.pixelSize: root.theme.sectionFontSize; font.bold: true }
                PlainText { text: root.rows.length + " of " + root.allRows.length + " records"; color: root.theme.muted; font.family: root.theme.dataFont; font.pixelSize: root.theme.captionFontSize }
            }
            IconButton { id: closeButton; iconName: "close"; tooltipText: "Close drawer"; onClicked: root.closed() }
        }

        TextField {
            width: parent.width
            placeholderText: "Filter this list…"
            text: root.filterText
            onTextChanged: root.filterText = text
        }

        Rectangle { width: parent.width; height: root.theme.dividerWidth; color: root.theme.border; opacity: root.theme.subtleDividerOpacity }

        ListView {
            width: parent.width
            height: parent.height - y
            model: root.rows
            reuseItems: true
            clip: true
            spacing: 4
            boundsBehavior: Flickable.StopAtBounds

            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

            delegate: CompactRow {
                required property var modelData
                width: ListView.view.width - 8
                height: 60
                theme: root.theme
                title: modelData.title
                subtitle: modelData.subtitle
                meta: modelData.meta
                idleColor: root.theme.quietSurface
                titleElide: Text.ElideMiddle
                horizontalPadding: 10
                textSpacing: 3
                interactive: root.selectionEnabled
                    && DetailDomains.selectable(root.domain)
                    && !!modelData.pid
                onClicked: root.processSelected(Number(modelData.pid))
            }
        }
    }
}
