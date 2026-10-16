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
    contentHeight: content.implicitHeight + 16
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    onVisibleChanged: if (!visible) limitsExpanded = false
    QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

    Column {
        id: content
        width: root.width - 10
        spacing: 20

        Column {
            width: parent.width
            spacing: 10
            topPadding: 8
            ReadingText {
                width: parent.width
                theme: root.theme
                text: root.assessment.context
                color: root.theme.muted
                font.pixelSize: root.theme.readingMetaFontSize
            }
            ReadingText {
                objectName: "xrayAssessmentHeadline"
                width: parent.width
                theme: root.theme
                text: root.assessment.headline
                font.pixelSize: root.theme.readingHeroFontSize
                font.weight: Font.DemiBold
            }
            ReadingText {
                width: parent.width
                theme: root.theme
                text: root.assessment.description
                color: root.theme.muted
                font.pixelSize: root.theme.readingLabelFontSize
                lineHeight: 1.25
            }
            ReadingButton {
                objectName: "xrayMeasurementLimits"
                theme: root.theme
                subtle: true
                leftPadding: 0
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
            Repeater {
                model: root.assessment.resources
                delegate: Item {
                    id: resource
                    required property var modelData
                    width: content.width
                    implicitHeight: resourceContent.implicitHeight + 28
                    Rectangle {
                        width: parent.width
                        height: root.theme.dividerWidth
                        color: root.theme.cardBorder
                    }
                    Column {
                        id: resourceContent
                        y: 14
                        width: parent.width
                        spacing: 7
                        Row {
                            width: parent.width
                            ReadingText {
                                width: parent.width - badge.width - 12
                                theme: root.theme
                                text: resource.modelData.label
                                color: root.theme.muted
                                font.pixelSize: root.theme.readingMetaFontSize
                            }
                            ReadingText {
                                id: badge
                                theme: root.theme
                                text: resource.modelData.badge === "PARTIAL" ? "Incomplete"
                                    : resource.modelData.badge === "PENDING" ? "Waiting for data"
                                    : resource.modelData.badge === "SYSTEM" ? "System-wide"
                                    : resource.modelData.badge === "OBSERVED" ? "Worth checking" : ""
                                color: resource.modelData.attention ? root.theme.storageAccent : root.theme.muted
                                font.pixelSize: root.theme.readingCaptionFontSize
                            }
                        }
                        ReadingText {
                            width: parent.width
                            theme: root.theme
                            text: resource.modelData.title
                            font.pixelSize: root.theme.readingTitleFontSize
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
            implicitHeight: nextStep.implicitHeight + 32
            radius: root.theme.panelRadius
            color: root.theme.surfaceMid
            Column {
                id: nextStep
                x: 16
                y: 16
                width: parent.width - 32
                spacing: 7
                ReadingText {
                    theme: root.theme
                    text: "Try the slow action again"
                    font.pixelSize: root.theme.readingLabelFontSize
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
            font.pixelSize: root.theme.readingCaptionFontSize
        }
    }
}
