import QtQuick
import QtQuick.Layouts
import "../cards"
import "../controls"
import "../DetailDomains.js" as DetailDomains

Item {
    id: root

    required property var theme
    property var snapshot: ({})
    property bool busy: false

    signal processSelected(int pid)
    signal detailsRequested(string domain)

    ColumnLayout {
        anchors.fill: parent
        spacing: root.theme.consoleGap

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: root.theme.consoleTopRowHeight
            Layout.minimumHeight: root.theme.consoleTopRowHeight
            Layout.maximumHeight: root.theme.consoleTopRowHeight
            spacing: root.theme.consoleGap

            IdentityCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 3
                Layout.minimumWidth: 0
                Layout.minimumHeight: 0
                theme: root.theme
                snapshot: root.snapshot
            }

            CauseCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 4
                Layout.minimumHeight: 0
                theme: root.theme
                snapshot: root.snapshot
                onDetailsRequested: root.detailsRequested(DetailDomains.Cause)
            }
            DevicesCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 4
                Layout.minimumHeight: 0
                theme: root.theme
                snapshot: root.snapshot
                onDetailsRequested: root.detailsRequested(DetailDomains.Devices)
            }
            RuntimeCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 3
                Layout.minimumHeight: 0
                theme: root.theme
                snapshot: root.snapshot
                onDetailsRequested: root.detailsRequested(DetailDomains.Runtime)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: root.theme.consoleGap

            ProcessConsole {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 11
                Layout.minimumWidth: 0
                Layout.minimumHeight: 0
                theme: root.theme
                snapshot: root.snapshot
                onProcessSelected: function(pid) { root.processSelected(pid) }
                onDetailsRequested: root.detailsRequested(DetailDomains.Processes)
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 9
                Layout.minimumWidth: 0
                Layout.minimumHeight: 0
                spacing: root.theme.consoleGap

                ConnectionsCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: 11
                    Layout.minimumHeight: 0
                    theme: root.theme
                    snapshot: root.snapshot
                    onDetailsRequested: root.detailsRequested(DetailDomains.Connections)
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: 9
                    Layout.minimumHeight: 0
                    spacing: root.theme.consoleGap

                    FilesCard {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: 11
                        Layout.minimumWidth: 0
                        Layout.minimumHeight: 0
                        theme: root.theme
                        snapshot: root.snapshot
                        onDetailsRequested: root.detailsRequested(DetailDomains.Files)
                    }
                    ExplanationsCard {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: 8
                        Layout.minimumWidth: 0
                        Layout.minimumHeight: 0
                        theme: root.theme
                        snapshot: root.snapshot
                        onDetailsRequested: root.detailsRequested(DetailDomains.Explanations)
                    }
                }
            }
        }
    }

    Rectangle {
        visible: !!(root.snapshot.target && root.snapshot.target.error)
        anchors.fill: parent
        radius: root.theme.consoleRadius
        color: root.theme.surfaceHigh
        border.color: root.theme.danger
        border.width: root.theme.borderWidth

        Column {
            anchors.centerIn: parent
            spacing: root.theme.smallGap
            PlainText {
                width: Math.min(520, root.width - 40)
                text: root.snapshot.target ? root.snapshot.target.error : ""
                color: root.theme.text
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.labelFontSize
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
            PlainText {
                width: Math.min(520, root.width - 40)
                text: "Try an app, PID, :port, file, service, or device query."
                color: root.theme.muted
                font.family: root.theme.dataFont
                font.pixelSize: root.theme.captionFontSize
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Rectangle {
        visible: root.busy
        anchors.fill: parent
        radius: root.theme.consoleRadius
        color: root.theme.busyScrim
        PlainText {
            anchors.centerIn: parent
            text: "SCANNING TARGET…"
            color: root.theme.accent
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.labelFontSize
            font.bold: true
            font.letterSpacing: root.theme.utilityTracking
        }
    }
}
