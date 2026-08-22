import QtQuick
import "../controls"
import "../Format.js" as Format
import "../DeviceSummary.js" as DeviceSummary
import "../DetailDomains.js" as DetailDomains

Card {
    id: root
    objectName: "xrayDevicesCard"

    property var snapshot: ({})
    readonly property var devices: snapshot.devices || {}
    readonly property var summary: DeviceSummary.summarize(devices)
    readonly property var rows: summary.rows
    readonly property var activeRows: summary.activeRows
    readonly property var limitedSources: summary.limitedSources
    readonly property int rowCount: Math.ceil(rows.length / 2)
    signal detailsRequested()

    title: DetailDomains.title(DetailDomains.Devices)
    accentColor: theme.deviceAccent
    countText: ""
    detailsCount: DetailDomains.count(DetailDomains.Devices, snapshot)
    interactive: true
    onClicked: detailsRequested()

    body: Grid {
        anchors.fill: parent
        anchors.topMargin: 5
        columns: 2
        spacing: 0

        Repeater {
            model: root.rows
            delegate: Item {
                id: deviceCell
                required property int index
                required property var modelData
                width: parent.width / 2
                height: parent.height / Math.max(1, root.rowCount)

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 1
                    radius: Math.max(2, root.theme.radius - 2)
                    color: deviceCell.modelData.active
                        ? root.theme.tintedSurface(root.accentColor)
                        : (deviceCell.modelData.limited
                            ? root.theme.dangerSurface
                            : root.theme.transparent)
                }

                Rectangle {
                    visible: deviceCell.modelData.active === true
                        || deviceCell.modelData.limited === true
                    width: 2
                    anchors.left: parent.left
                    anchors.leftMargin: 1
                    anchors.top: parent.top
                    anchors.topMargin: 5
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 5
                    radius: 1
                    color: deviceCell.modelData.limited ? root.theme.danger : root.accentColor
                }

                Rectangle {
                    visible: deviceCell.index % 2 === 0
                    width: root.theme.dividerWidth
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    color: root.theme.border
                }
                Rectangle {
                    visible: deviceCell.index < root.rows.length - 2
                    height: root.theme.dividerWidth
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    color: root.theme.border
                }

                Rectangle {
                    width: 20
                    height: 20
                    radius: 10
                    anchors.left: parent.left
                    anchors.leftMargin: 7
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.theme.transparent
                    border.color: deviceCell.modelData.limited
                        ? root.theme.danger
                        : (deviceCell.modelData.active ? root.accentColor : root.theme.border)
                    border.width: root.theme.borderWidth
                    PlainText {
                        anchors.centerIn: parent
                        text: Format.icon(deviceCell.modelData.icon)
                        color: deviceCell.modelData.limited
                            ? root.theme.danger
                            : (deviceCell.modelData.active ? root.accentColor : root.theme.muted)
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.captionFontSize
                    }
                }

                Column {
                    anchors.left: parent.left
                    anchors.leftMargin: 34
                    anchors.right: stateText.left
                    anchors.rightMargin: stateText.visible ? 5 : 7
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 0
                    PlainText {
                        width: parent.width
                        text: deviceCell.modelData.title
                        color: root.theme.text
                        font.family: root.theme.bodyFont
                        font.pixelSize: root.theme.captionFontSize
                        font.bold: deviceCell.modelData.active === true
                        elide: Text.ElideRight
                    }
                    PlainText {
                        width: parent.width
                        text: deviceCell.modelData.subtitle
                        color: root.theme.muted
                        font.family: root.theme.dataFont
                        font.pixelSize: root.theme.microFontSize
                        elide: Text.ElideRight
                    }
                }

                PlainText {
                    id: stateText
                    visible: text !== ""
                    anchors.right: parent.right
                    anchors.rightMargin: 7
                    anchors.verticalCenter: parent.verticalCenter
                    text: deviceCell.modelData.meta
                    color: deviceCell.modelData.limited
                        ? root.theme.danger
                        : (deviceCell.modelData.active ? root.accentColor : root.theme.muted)
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                    font.bold: deviceCell.modelData.active === true
                        || deviceCell.modelData.limited === true
                }
            }
        }
    }
}
