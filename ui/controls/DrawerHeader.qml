import QtQuick

Item {
    id: root

    required property var theme
    property color accentColor: theme.accent
    property string eyebrow: "INSPECTOR"
    property string title: ""
    property string detail: ""
    signal closed()

    height: theme.drawerHeaderHeight

    Column {
        anchors.left: parent.left
        anchors.right: closeButton.left
        anchors.rightMargin: root.theme.gap
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Row {
            width: parent.width
            spacing: root.theme.gap

            PlainText {
                width: Math.max(0, parent.width - contextLabel.width - root.theme.gap)
                text: root.title
                color: root.theme.text
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.summaryFontSize
                font.bold: true
                elide: Text.ElideRight
            }
            PlainText {
                id: contextLabel
                visible: root.eyebrow !== ""
                width: visible ? implicitWidth : 0
                text: root.eyebrow.toUpperCase()
                color: root.accentColor
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.microFontSize
                font.bold: true
                font.letterSpacing: root.theme.utilityTracking
            }
        }

        PlainText {
            visible: root.detail !== ""
            width: parent.width
            text: root.detail
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            elide: Text.ElideRight
        }
    }

    IconButton {
        id: closeButton
        theme: root.theme
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        iconName: "close"
        tooltipText: "Close drawer"
        onClicked: root.closed()
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: root.theme.dividerWidth
        color: root.accentColor
        opacity: 0.78
    }
}
