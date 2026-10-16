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
    implicitHeight: header.height + (expanded ? details.implicitHeight + 20 : 0) + 1
    objectName: "xrayPerformanceCheck"

    QQC.AbstractButton {
        id: header
        width: parent.width
        height: headingColumn.implicitHeight + 28
        focusPolicy: Qt.StrongFocus
        hoverEnabled: true
        Accessible.name: root.heading + ", " + root.statusText
        Accessible.description: root.expanded ? "Hide evidence" : "Show evidence"
        onClicked: root.toggled()
        onActiveFocusChanged: if (activeFocus) root.focused()
        background: Rectangle {
            radius: 6
            color: header.hovered ? root.theme.controlHoverSurface : root.theme.transparent
            border.width: header.visualFocus ? root.theme.borderWidth : 0
            border.color: root.theme.accent
        }
        contentItem: Item {
            Column {
                id: headingColumn
                x: 8
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - status.width - 42
                spacing: 5
                ReadingText {
                    width: parent.width
                    theme: root.theme
                    text: root.heading
                    font.pixelSize: root.theme.readingLabelFontSize
                    font.weight: Font.Medium
                }
                ReadingText {
                    width: parent.width
                    theme: root.theme
                    text: root.scopeLabel
                    color: root.theme.muted
                    font.pixelSize: root.theme.readingCaptionFontSize
                    wrapMode: Text.NoWrap
                    elide: Text.ElideMiddle
                }
            }
            ReadingText {
                id: status
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                theme: root.theme
                text: root.statusText + (root.expanded ? "   −" : "   +")
                color: root.row.tone === "attention" ? root.theme.storageAccent : root.theme.muted
                font.pixelSize: root.theme.readingCaptionFontSize
            }
        }
    }

    Column {
        id: details
        visible: root.expanded
        y: header.height
        x: 8
        width: parent.width - 16
        spacing: 14
        ReadingText {
            width: parent.width
            theme: root.theme
            text: root.row.subtitle || ""
            color: root.theme.muted
            lineHeight: 1.3
        }
        Rectangle {
            width: parent.width
            implicitHeight: evidence.implicitHeight + 24
            radius: 6
            color: root.theme.surfaceMid
            Column {
                id: evidence
                x: 12
                y: 12
                width: parent.width - 24
                spacing: 10
                Repeater {
                    model: root.expanded ? root.row.evidence || [] : []
                    delegate: ReadingText {
                        required property string modelData
                        width: evidence.width
                        theme: root.theme
                        text: modelData
                        font.family: root.theme.codeFont
                        font.pixelSize: root.theme.readingCaptionFontSize
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
                    font.pixelSize: root.theme.readingCaptionFontSize
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
        opacity: 0.55
    }
}
