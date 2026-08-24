import QtQuick
import "../controls"
import "../Format.js" as Format

Card {
    id: root
    objectName: "xrayIdentityCard"

    property var snapshot: ({})
    readonly property var context: snapshot.context || {}
    readonly property var window: context.window || {}
    title: "Selected target"
    countText: snapshot.target && snapshot.target.rootPid ? "PID " + snapshot.target.rootPid : ""

    body: Item {
        anchors.fill: parent

        Rectangle {
            anchors.fill: parent
            anchors.topMargin: 4
            radius: root.theme.controlRadius
            color: root.theme.surfaceLow
            border.color: root.theme.cardBorder
            border.width: root.theme.borderWidth
            clip: true

            Image {
                id: previewImage
                anchors.fill: parent
                source: root.context.previewPath ? "file://" + root.context.previewPath : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                cache: false
                visible: status === Image.Ready
                opacity: root.theme.previewOpacity
            }

            Column {
                visible: !previewImage.visible && !!(root.snapshot.target && root.snapshot.target.rootPid)
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: -10
                spacing: 6

                PlainText {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: Format.icon("window")
                    color: root.theme.sectionText
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.heroFontSize
                }
                PlainText {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.context.previewStatus === "pending" || root.context.previewPath
                        ? "LOADING WINDOW PREVIEW"
                        : root.context.previewStatus === "failed"
                        ? "WINDOW PREVIEW FAILED"
                        : root.context.previewStatus === "unavailable"
                        ? "WINDOW PREVIEW UNAVAILABLE"
                        : root.context.previewStatus === "deferred"
                        ? "PREVIEW UPDATES WHEN X-RAY OPENS"
                        : "WINDOW PREVIEW OFF"
                    color: root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                    font.letterSpacing: root.theme.labelTracking
                }
                PlainText {
                    visible: root.context.previewStatus === "failed"
                        && !!root.context.previewError
                    width: Math.min(implicitWidth, root.width - 32)
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.context.previewError || ""
                    color: root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.microFontSize
                    elide: Text.ElideMiddle
                }
            }

            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    GradientStop { position: 0.0; color: root.theme.transparent }
                    GradientStop { position: 1.0; color: root.theme.surfaceMid }
                }
            }

            Column {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 11
                spacing: 3

                PlainText {
                    width: parent.width
                    text: root.window.title || Format.firstCommand(root.context.command) || "Choose a target to inspect"
                    color: root.theme.text
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.summaryFontSize
                    font.bold: true
                    elide: Text.ElideRight
                }
                PlainText {
                    width: parent.width
                    text: root.context.executable || "Search above to begin"
                    color: root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: root.theme.captionFontSize
                    elide: Text.ElideMiddle
                }
            }
        }
    }
}
