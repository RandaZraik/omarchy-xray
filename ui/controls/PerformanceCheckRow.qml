import QtQuick
import QtQuick.Controls as QQC

Item {
    id: root
    required property var theme
    required property var row
    property bool expanded: false
    signal toggled()
    signal focused()
    function focusHeader() { header.forceActiveFocus(Qt.OtherFocusReason) }
    readonly property string heading: String(row.title || "Measurement").split(" · ")[0]
    readonly property string statusText: ({"QUIET": "No signal", "OBSERVED": "Observed", "UNAVAILABLE": "Unavailable", "BASELINE": "Collecting", "LIMITED": "Incomplete"})[row.meta] || String(row.meta || "Unavailable")
    readonly property string scopeLabel: row.scope === "Host" ? "Whole computer"
        : String(row.scope || "").indexOf("Cgroup ") === 0
            ? "Shared group · " + String(row.scope).split("/").pop()
            : row.scope === "Selected tree" ? "Selected processes"
            : row.scope === "Selected threads" ? "Selected threads" : "Measurement coverage"
    implicitHeight: header.height + (expanded ? details.implicitHeight + root.theme.gap * 2 : 0) + root.theme.dividerWidth
    objectName: "xrayPerformanceCheck"

    QQC.AbstractButton {
        id: header
        width: parent.width
        height: headingColumn.implicitHeight + root.theme.pad * 2
        focusPolicy: Qt.StrongFocus
        hoverEnabled: true
        Accessible.name: root.heading + ", " + root.statusText
        Accessible.description: root.expanded ? "Hide evidence" : "Show evidence"
        onClicked: root.toggled()
        onActiveFocusChanged: if (activeFocus) root.focused()
        background: Rectangle {
            radius: root.theme.controlRadius
            color: header.hovered ? root.theme.controlHoverSurface : root.theme.transparent
            border.width: header.visualFocus ? root.theme.borderWidth : 0
            border.color: root.theme.accent
        }
        contentItem: Item {
            Column {
                id: headingColumn
                x: root.theme.pad
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - status.width - root.theme.pad * 2 - root.theme.gap
                spacing: root.theme.smallGap
                ReadingText {
                    width: parent.width
                    theme: root.theme
                    text: root.heading
                    font.pixelSize: root.theme.labelFontSize
                    font.weight: Font.Medium
                }
                ReadingText {
                    width: parent.width
                    theme: root.theme
                    text: root.scopeLabel
                    color: root.theme.muted
                    font.pixelSize: root.theme.microFontSize
                    wrapMode: Text.NoWrap
                    elide: Text.ElideMiddle
                }
            }
            ReadingText {
                id: status
                anchors.right: parent.right
                anchors.rightMargin: root.theme.pad
                anchors.verticalCenter: parent.verticalCenter
                theme: root.theme
                text: root.statusText + (root.expanded ? "   −" : "   +")
                color: root.row.tone === "attention" ? root.theme.storageAccent : root.theme.muted
                font.pixelSize: root.theme.microFontSize
            }
        }
    }

    Column {
        id: details
        visible: root.expanded
        y: header.height
        x: root.theme.pad
        width: parent.width - root.theme.pad * 2
        spacing: root.theme.gap
        ReadingText {
            width: parent.width
            theme: root.theme
            text: root.row.subtitle || ""
            color: root.theme.muted
            lineHeight: 1.3
        }
        Rectangle {
            width: parent.width
            implicitHeight: evidence.implicitHeight + root.theme.pad * 2
            radius: root.theme.controlRadius
            color: root.theme.surfaceMid
            Column {
                id: evidence
                x: root.theme.pad
                y: root.theme.pad
                width: parent.width - root.theme.pad * 2
                spacing: root.theme.gap
                Repeater {
                    model: root.expanded ? root.row.evidence || [] : []
                    delegate: ReadingText {
                        required property string modelData
                        width: evidence.width
                        theme: root.theme
                        text: modelData
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
                        wrapMode: Text.Wrap
                        lineHeight: 1.35
                    }
                }
                ReadingText {
                    visible: Number(root.row.evidenceCount || 0) > (root.row.evidence || []).length
                    width: parent.width
                    theme: root.theme
                    text: Math.max(0, Number(root.row.evidenceCount || 0) - (root.row.evidence || []).length) + " additional records omitted"
                    color: root.theme.muted
                    font.pixelSize: root.theme.microFontSize
                }
            }
        }
        ReadingText {
            visible: !!root.row.nextStep
            width: parent.width
            theme: root.theme
            text: root.row.nextStep || ""
            color: root.theme.muted
            lineHeight: 1.3
        }
    }

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: root.theme.dividerWidth
        color: root.theme.cardBorder
        opacity: root.theme.dividerOpacity
    }
}
