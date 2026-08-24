import QtQuick
import QtQuick.Layouts
import "../cards"
import "../controls"
import "../DetailDomains.js" as DetailDomains

Item {
    id: root

    required property var theme
    property var snapshot: ({})
    property var performanceSamples: []
    property int performanceWindowSeconds: 60
    property bool busy: false

    signal processSelected(int pid)
    signal detailsRequested(string domain)

    RowLayout {
        anchors.fill: parent
        spacing: root.theme.gap

        ColumnLayout {
            Layout.fillHeight: true
            Layout.preferredWidth: parent.width * 0.27
            spacing: root.theme.gap

            IdentityCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 190
                theme: root.theme
                snapshot: root.snapshot
            }
            CauseCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 166
                theme: root.theme
                snapshot: root.snapshot
                onDetailsRequested: root.detailsRequested(DetailDomains.Cause)
            }
            ProcessCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                theme: root.theme
                snapshot: root.snapshot
                onProcessSelected: function(pid) { root.processSelected(pid); }
                onDetailsRequested: root.detailsRequested(DetailDomains.Processes)
            }
        }

        ColumnLayout {
            Layout.fillHeight: true
            Layout.preferredWidth: parent.width * 0.45
            spacing: root.theme.gap

            PerformanceCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 204
                theme: root.theme
                samples: root.performanceSamples
                windowSeconds: root.performanceWindowSeconds
            }
            ConnectionsCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                theme: root.theme
                snapshot: root.snapshot
                onDetailsRequested: root.detailsRequested(DetailDomains.Connections)
            }
            FilesCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 188
                theme: root.theme
                snapshot: root.snapshot
                onDetailsRequested: root.detailsRequested(DetailDomains.Files)
            }
        }

        ColumnLayout {
            Layout.fillHeight: true
            Layout.preferredWidth: parent.width * 0.28
            spacing: root.theme.gap

            DevicesCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 190
                theme: root.theme
                snapshot: root.snapshot
                onDetailsRequested: root.detailsRequested(DetailDomains.Devices)
            }
            RuntimeCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 174
                theme: root.theme
                snapshot: root.snapshot
                onDetailsRequested: root.detailsRequested(DetailDomains.Runtime)
            }
            ExplanationsCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                theme: root.theme
                snapshot: root.snapshot
                onDetailsRequested: root.detailsRequested(DetailDomains.Explanations)
            }
        }
    }

    Rectangle {
        visible: !!(root.snapshot.target && root.snapshot.target.error)
        anchors.fill: parent
        radius: root.theme.cardRadius
        color: root.theme.surfaceHigh
        border.color: root.theme.cardBorder
        border.width: root.theme.borderWidth

        Column {
            anchors.centerIn: parent
            spacing: 8
            PlainText {
                width: Math.min(420, root.width - 40)
                text: root.snapshot.target ? root.snapshot.target.error : ""
                color: root.theme.text
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.sectionFontSize
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
            PlainText {
                width: Math.min(420, root.width - 40)
                text: "Try another application, PID, :port, file path, or resource."
                color: root.theme.muted
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.bodyFontSize
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
        }
    }

    Rectangle {
        visible: root.busy
        anchors.fill: parent
        radius: root.theme.cardRadius
        color: root.theme.busyScrim
        PlainText {
            anchors.centerIn: parent
            text: "Inspecting target…"
            color: root.theme.text
            font.family: root.theme.dataFont
            font.pixelSize: root.theme.labelFontSize
            font.letterSpacing: root.theme.labelTracking
        }
    }
}
