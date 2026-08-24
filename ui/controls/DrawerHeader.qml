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

    Rectangle {
        width: 7
        height: 7
        radius: root.theme.pillRadius
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.topMargin: root.theme.smallGap
        color: root.accentColor

        Rectangle {
            anchors.centerIn: parent
            width: parent.width + root.theme.gap
            height: width
            radius: root.theme.pillRadius
            color: root.theme.withAlpha(root.accentColor, 0.16)
        }
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: root.theme.gap + root.theme.smallGap
        anchors.right: closeButton.left
        anchors.rightMargin: root.theme.gap
        anchors.verticalCenter: parent.verticalCenter
        spacing: 3

        PlainText {
            width: parent.width
            text: root.eyebrow.toUpperCase()
            color: root.accentColor
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.microFontSize
            font.bold: true
            font.letterSpacing: root.theme.utilityTracking
            elide: Text.ElideRight
        }

        PlainText {
            width: parent.width
            text: root.title
            color: root.theme.text
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.sectionFontSize
            font.bold: true
            elide: Text.ElideRight
        }

        PlainText {
            visible: root.detail !== ""
            width: parent.width
            text: root.detail
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.captionFontSize
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
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: root.accentColor }
            GradientStop {
                position: 0.42
                color: root.theme.withAlpha(root.accentColor, 0.12)
            }
            GradientStop { position: 1; color: root.theme.transparent }
        }
    }
}
