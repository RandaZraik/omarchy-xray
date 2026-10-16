import QtQuick
import QtQuick.Controls as QQC
import "../controls"
import "../domains/PerformanceAssessment.js" as PerformanceAssessment

Flickable {
    id: root
    required property var theme
    property var performance: ({})
    property bool limitsExpanded: false
    readonly property var assessment: PerformanceAssessment.assessment(performance)
    objectName: "xrayPerformanceOverview"
    contentHeight: content.implicitHeight + theme.gap
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    onVisibleChanged: if (!visible) limitsExpanded = false
    QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

    Column {
        id: content
        width: root.width - root.theme.drawerListInset
        spacing: root.theme.gap * 2

        Column {
            width: parent.width
            spacing: root.theme.gap
            topPadding: root.theme.smallGap
            ReadingText {
                width: parent.width
                theme: root.theme
                text: root.assessment.context
                color: root.theme.muted
                font.pixelSize: root.theme.microFontSize
            }
            ReadingText {
                objectName: "xrayAssessmentHeadline"
                width: parent.width
                theme: root.theme
                text: root.assessment.headline
                font.pixelSize: root.theme.sectionFontSize
                font.weight: Font.DemiBold
            }
            ReadingText {
                width: parent.width
                theme: root.theme
                text: root.assessment.description
                color: root.theme.muted
                font.pixelSize: root.theme.bodyFontSize
                lineHeight: 1.25
            }
            ActionButton {
                objectName: "xrayMeasurementLimits"
                theme: root.theme
                accentColor: root.theme.processAccent
                text: (root.limitsExpanded ? "−  " : "+  ") + root.assessment.coverageLabel
                Accessible.name: "Measurement limits"
                Accessible.description: root.assessment.coverageLabel
                onClicked: root.limitsExpanded = !root.limitsExpanded
            }
            ReadingText {
                visible: root.limitsExpanded
                width: parent.width
                theme: root.theme
                text: root.assessment.limitations
                color: root.theme.muted
                lineHeight: 1.3
            }
        }

        Column {
            width: parent.width
            spacing: root.theme.gap
            Repeater {
                model: root.assessment.resources
                delegate: Rectangle {
                    id: resource
                    required property var modelData
                    required property int index
                    readonly property color accentColor: [root.theme.cpuAccent, root.theme.memoryAccent, root.theme.storageAccent][index]
                    width: content.width
                    implicitHeight: resourceContent.implicitHeight + root.theme.pad * 2
                    radius: root.theme.cardRadius
                    color: root.theme.surfaceLow
                    border.width: root.theme.borderWidth
                    border.color: root.theme.cardBorder
                    Rectangle {
                        width: root.theme.telemetryRailWidth
                        height: parent.height
                        color: resource.accentColor
                    }
                    Column {
                        id: resourceContent
                        x: root.theme.pad
                        y: root.theme.pad
                        width: parent.width - root.theme.pad * 2
                        spacing: root.theme.gap
                        Row {
                            width: parent.width
                            ReadingText {
                                width: parent.width - badge.width - root.theme.gap
                                theme: root.theme
                                text: resource.modelData.label
                                color: resource.accentColor
                                font.pixelSize: root.theme.labelFontSize
                                font.bold: true
                            }
                            ReadingText {
                                id: badge
                                theme: root.theme
                                text: resource.modelData.badge === "PARTIAL" ? "Incomplete"
                                    : resource.modelData.badge === "PENDING" ? "Waiting for data"
                                    : resource.modelData.badge === "SYSTEM" ? "System-wide"
                                    : resource.modelData.badge === "OBSERVED" ? "Worth checking" : ""
                                color: resource.modelData.attention ? root.theme.storageAccent : root.theme.muted
                                font.pixelSize: root.theme.microFontSize
                            }
                        }
                        ReadingText {
                            width: parent.width
                            theme: root.theme
                            text: resource.modelData.title
                            font.pixelSize: root.theme.summaryFontSize
                            font.weight: Font.Medium
                        }
                        ReadingText {
                            width: parent.width
                            theme: root.theme
                            text: resource.modelData.detail
                            color: root.theme.muted
                        }
                    }
                }
            }
        }

        Rectangle {
            width: parent.width
            implicitHeight: nextStep.implicitHeight + root.theme.pad * 2
            radius: root.theme.cardRadius
            color: root.theme.surfaceLow
            border.width: root.theme.borderWidth
            border.color: root.theme.cardBorder
            Column {
                id: nextStep
                x: root.theme.pad
                y: root.theme.pad
                width: parent.width - root.theme.pad * 2
                spacing: root.theme.gap
                ReadingText {
                    theme: root.theme
                    text: "Try the slow action again"
                    font.pixelSize: root.theme.labelFontSize
                    font.weight: Font.DemiBold
                }
                ReadingText {
                    width: parent.width
                    theme: root.theme
                    text: "Keep this open while it happens. Check whether the measurements change at the same time."
                    color: root.theme.muted
                    lineHeight: 1.25
                }
            }
        }

        ReadingText {
            width: parent.width
            theme: root.theme
            text: "A quiet sample doesn’t rule out a slowdown."
            color: root.theme.muted
            font.pixelSize: root.theme.microFontSize
        }
    }
}
