import QtQuick
import "../controls"
import "../Format.js" as Format
import "../TargetSearch.js" as TargetSearch

Rectangle {
    id: root
    objectName: "xrayTargetPalette"

    property var theme
    property var catalog: ({})
    property string query: ""
    property int currentIndex: -1
    signal selected(string query)
    readonly property string needle: query.trim().toLowerCase()
    readonly property var matches: TargetSearch.matches(query, catalog, 6)
    readonly property bool searching: needle.length > 0
    implicitHeight: searching ? 34 + Math.max(1, matches.length) * 38 + 10 : 54
    radius: theme.radius
    color: theme.panel
    border.color: theme.border
    border.width: theme.borderWidth
    clip: true

    onMatchesChanged: currentIndex = matches.length > 0 ? 0 : -1

    function moveSelection(delta) {
        if (!matches.length) return;
        currentIndex = (currentIndex + delta + matches.length) % matches.length;
    }

    function acceptCurrent() {
        if (!visible || currentIndex < 0 || currentIndex >= matches.length) return false;
        selected(matches[currentIndex].query);
        return true;
    }

    Column {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 2

        Row {
            visible: !root.searching
            width: parent.width
            height: visible ? 40 : 0
            spacing: 6

            Repeater {
                model: root.catalog.quickTargets || []
                delegate: Rectangle {
                    required property var modelData
                    anchors.verticalCenter: parent.verticalCenter
                    height: 28
                    width: chipText.implicitWidth + 18
                    radius: 14
                    color: chipHover.hovered ? root.theme.selected : root.theme.quietSurface
                    border.color: root.theme.border
                    border.width: root.theme.borderWidth
                    PlainText { id: chipText; anchors.centerIn: parent; text: modelData.label; color: root.theme.text; font.family: root.theme.bodyFont; font.pixelSize: root.theme.captionFontSize }
                    HoverHandler { id: chipHover }
                    TapHandler { onTapped: root.selected(modelData.query) }
                }
            }

            PlainText {
                id: queryHint
                anchors.verticalCenter: parent.verticalCenter
                text: "PID · :port · /path · service:name · container:name"
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.captionFontSize
            }
        }

        Row {
            visible: root.searching && root.matches.length > 0
            width: parent.width
            height: visible ? 28 : 0
            PlainText {
                id: resultCount
                anchors.verticalCenter: parent.verticalCenter
                text: root.matches.length + (root.matches.length === 1 ? " MATCH" : " MATCHES")
                color: root.theme.accent
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.captionFontSize
                font.bold: true
            }
            Item { width: Math.max(0, parent.width - resultCount.implicitWidth - keyboardHint.implicitWidth); height: 1 }
            PlainText {
                id: keyboardHint
                anchors.verticalCenter: parent.verticalCenter
                text: "↑↓ SELECT  ·  ENTER INSPECT"
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.microFontSize
            }
        }

        Repeater {
            model: root.matches
            delegate: CompactRow {
                required property int index
                required property var modelData
                width: parent.width
                height: 36
                theme: root.theme
                title: modelData.title
                subtitle: modelData.subtitle
                meta: Format.icon(modelData.kind)
                selected: index === root.currentIndex
                onClicked: root.selected(modelData.query)
            }
        }

        Item {
            visible: root.searching && root.matches.length === 0
            width: parent.width
            height: visible ? 36 : 0
            PlainText {
                anchors.left: parent.left
                anchors.leftMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: "No suggestions · Press Enter to inspect “" + root.query + "”"
                color: root.theme.muted
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.bodyFontSize
                elide: Text.ElideRight
                width: parent.width - 16
            }
        }
    }
}
