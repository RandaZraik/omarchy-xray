import QtQuick
import qs.Commons

QtObject {
    function withAlpha(base, alpha) {
        return Qt.rgba(base.r, base.g, base.b, Math.max(0, Math.min(1, alpha)));
    }

    function blend(base, tint, amount) {
        var weight = Math.max(0, Math.min(1, Number(amount || 0)));
        return Qt.rgba(
            base.r * (1 - weight) + tint.r * weight,
            base.g * (1 - weight) + tint.g * weight,
            base.b * (1 - weight) + tint.b * weight,
            1
        );
    }

    function tintedSurface(tint) {
        return blend(panel, tint, tintedSurfaceMix);
    }

    function hoveredBorder(tint) {
        return blend(cardBorder, tint, hoverBorderMix);
    }

    function headingColor(tint) {
        return blend(text, tint, headingAccentMix);
    }

    function spectralColor(hue, saturation) {
        var darkTheme = canvas.hslLightness < 0.52;
        var value = darkTheme ? 0.96 : 0.62;
        var chroma = darkTheme ? saturation : Math.min(0.82, saturation * 1.1);
        return blend(Qt.hsva(hue, chroma, value, 1), accent, 0.08);
    }

    readonly property color canvas: Color.background
    readonly property color panel: blend(Color.background, Color.menu.text, 0.018)
    readonly property color text: Color.menu.text
    readonly property color accent: Color.accent
    readonly property color danger: Color.urgent
    readonly property color border: blend(panel, text, 0.18)
    readonly property color selected: Color.menu.selectedBackground
    readonly property color scrim: withAlpha(canvas, 0.82)
    readonly property color transparent: withAlpha(panel, 0)

    // A restrained spectrum makes the instrument easier to read: a color
    // always means the same domain, while Omarchy's accent still anchors the
    // shell and selection state.
    readonly property color cpuAccent: spectralColor(0.61, 0.58)
    readonly property color processAccent: spectralColor(0.64, 0.62)
    readonly property color memoryAccent: spectralColor(0.77, 0.58)
    readonly property color networkAccent: spectralColor(0.51, 0.62)
    readonly property color storageAccent: spectralColor(0.105, 0.68)
    readonly property color deviceAccent: spectralColor(0.46, 0.56)
    readonly property color runtimeAccent: spectralColor(0.25, 0.62)
    readonly property color alertAccent: danger

    // Surface depth is derived from Omarchy's active background, foreground,
    // and accent. The dashboard stays calm while cards, navigation, and the
    // selected-target strip remain visually distinct in both dark and light
    // themes.
    readonly property real mutedTextMix: 0.48
    readonly property real quietSurfaceMix: 0.04
    readonly property real previewSurfaceMix: 0.045
    readonly property real controlFocusSurfaceMix: 0.085
    readonly property real controlFocusBorderMix: 0.32
    readonly property real controlActiveSurfaceMix: 0.075
    readonly property real controlHoverSurfaceMix: 0.055
    readonly property real tintedSurfaceMix: 0.075
    readonly property real dangerSurfaceMix: 0.085
    readonly property real cardBorderTextMix: 0.16
    readonly property real accentBorderMix: 0.32
    readonly property real sectionAccentMix: 0.28
    readonly property real metricAccentMix: 0.46
    readonly property real gridAccentMix: 0.24
    readonly property real hoverBorderMix: 0.34
    readonly property real headingAccentMix: 0.58
    readonly property color muted: blend(Color.muted, text, mutedTextMix)
    readonly property color quietSurface: blend(panel, text, quietSurfaceMix)
    readonly property color previewSurface: blend(quietSurface, accent, previewSurfaceMix)
    readonly property color controlFocusSurface: blend(
        quietSurface, accent, controlFocusSurfaceMix
    )
    readonly property color controlFocusBorder: blend(
        cardBorder, accent, controlFocusBorderMix
    )
    readonly property color controlActiveSurface: blend(
        quietSurface, text, controlActiveSurfaceMix
    )
    readonly property color controlHoverSurface: blend(
        quietSurface, text, controlHoverSurfaceMix
    )
    readonly property color dangerSurface: blend(panel, danger, dangerSurfaceMix)
    readonly property color cardBorder: blend(panel, text, cardBorderTextMix)
    readonly property color accentBorder: blend(border, accent, accentBorderMix)
    readonly property color sectionText: blend(text, accent, sectionAccentMix)
    readonly property color metricText: blend(text, accent, metricAccentMix)
    readonly property color grid: blend(panel, accent, gridAccentMix)
    readonly property color surfaceLow: blend(panel, text, 0.028)
    readonly property color surfaceMid: blend(panel, text, 0.052)
    readonly property color surfaceHigh: blend(panel, text, 0.082)
    readonly property color surfaceHighlight: withAlpha(text, 0.075)
    readonly property color accentSurface: blend(panel, accent, 0.075)
    readonly property color accentSurfaceStrong: blend(panel, accent, 0.13)
    readonly property color accentGlow: withAlpha(accent, 0.17)
    readonly property color accentGlowSoft: withAlpha(accent, 0.075)
    readonly property color drawerScrim: withAlpha(canvas, 0.68)
    readonly property color busyScrim: withAlpha(panel, 0.88)
    readonly property color confirmationScrim: withAlpha(canvas, 0.84)
    readonly property color trace: cpuAccent
    readonly property color secondaryTrace: memoryAccent

    // Reserve semantic colors for abnormal process states.
    readonly property color inspectorAccent: processAccent
    readonly property color inspectorAccentText: headingColor(processAccent)
    readonly property color inspectorTableSurface: surfaceMid
    readonly property color inspectorHeaderSurface: surfaceHigh
    readonly property color inspectorRaisedSurface: surfaceHigh
    readonly property color inspectorSelectedSurface: blend(panel, processAccent, 0.13)

    readonly property string displayFont: Style.font.family
    readonly property string bodyFont: displayFont
    readonly property string dataFont: Style.font.family
    readonly property int microFontSize: Style.font.caption
    readonly property int captionFontSize: Style.font.caption
    readonly property int bodyFontSize: Style.font.bodySmall
    readonly property int labelFontSize: Style.font.body
    readonly property int summaryFontSize: Style.font.subtitle
    readonly property int sectionFontSize: Style.font.heading
    readonly property int metricFontSize: Style.font.heading
    readonly property int heroFontSize: Style.font.display
    readonly property real headingTracking: 0.7
    readonly property real utilityTracking: 0.8
    readonly property real labelTracking: 1.1
    readonly property real brandTracking: 2.4
    readonly property real taglineTracking: 1.2
    readonly property int radius: Math.max(10, Style.cornerRadius)
    readonly property int panelRadius: Math.max(16, radius + 6)
    readonly property int cardRadius: Math.max(12, radius + 2)
    readonly property int controlRadius: Math.max(8, radius - 2)
    readonly property int pillRadius: 999
    readonly property int gap: Style.space(10)
    readonly property int smallGap: Style.space(6)
    readonly property int pad: Style.space(12)
    readonly property int panelPadding: Style.space(18)
    readonly property int panelMaxWidth: Style.space(1400)
    readonly property int panelMaxHeight: Style.space(840)
    readonly property int targetBrowserWidth: Style.space(264)
    readonly property int targetBrowserOverlayWidth: Style.space(304)
    readonly property int targetBrowserPinnedWidth: Style.space(1180)
    readonly property int targetBrowserContentPadding: Style.space(10)
    readonly property int targetBrowserHeaderHeight: Style.space(38)
    readonly property int targetBrowserCloseSize: Style.space(28)
    readonly property int targetBrowserSearchHeight: Style.space(38)
    readonly property int targetBrowserFilterHeight: Style.space(30)
    readonly property int targetBrowserRowHeight: Style.space(44)
    readonly property int targetBrowserSectionHeight: Style.space(26)
    readonly property int targetBrowserBeamWidth: Math.max(2, borderWidth * 2)
    readonly property int cardHeaderHeight: Style.space(38)
    readonly property int evidenceHeaderHeight: Style.space(28)
    readonly property int evidenceRowHeight: Style.space(31)
    readonly property int drawerMargin: Style.space(10)
    readonly property int drawerPadding: Style.space(20)
    readonly property int drawerHeaderHeight: Style.space(64)
    readonly property int processEvidenceExpandedWidth: Style.space(720)
    // Dense system data still has to be comfortably scannable at native
    // monitor scale. Keep these above the shell's caption-size defaults.
    readonly property int processEvidenceHeaderFontSize: Math.max(
        bodyFontSize, labelFontSize
    )
    readonly property int processEvidencePrimaryFontSize: Math.max(
        labelFontSize, summaryFontSize
    )
    readonly property int processEvidenceValueFontSize: Math.max(
        labelFontSize, summaryFontSize
    )
    readonly property int processEvidenceSecondaryFontSize: Math.max(
        bodyFontSize, labelFontSize
    )
    readonly property int processEvidenceBadgeFontSize: Math.max(
        microFontSize, bodyFontSize
    )
    readonly property int processEvidenceCommandHeight: Style.space(78)
    readonly property int processEvidenceHeaderHeight: Style.space(42)
    readonly property int processEvidenceRowHeight: Style.space(64)
    readonly property int processEvidenceIndent: Style.space(8)
    readonly property int processEvidenceBranchWidth: Style.space(9)
    readonly property int processEvidenceMaximumDepth: 7
    readonly property int telemetryHeight: Style.space(82)
    readonly property int telemetryTargetWidth: Style.space(340)
    readonly property int telemetryTargetMinimumWidth: Style.space(240)
    readonly property int telemetryMetricWidth: Style.space(132)
    readonly property int telemetryMetricMinimumWidth: Style.space(86)
    readonly property int telemetryModulePadding: Style.space(12)
    readonly property int telemetryRailWidth: Math.max(2, borderWidth * 2)
    readonly property int telemetrySignalHeight: Math.max(2, borderWidth * 2)
    readonly property int performanceLegendHeight: Style.space(24)
    readonly property int performanceLegendSwatchWidth: Style.space(18)
    readonly property int performanceTimelineHeight: Style.space(16)
    readonly property int performancePlotPadding: Style.space(4)
    readonly property real performanceGridOpacity: 0.48
    readonly property real performanceFillOpacity: 0.16
    readonly property real performanceScaleHeadroom: 1.24
    readonly property real performanceMemoryPadding: 0.025
    readonly property real performancePrimaryTraceWidth: Math.max(2, borderWidth * 2)
    readonly property real performanceSecondaryTraceWidth: Math.max(1.5, borderWidth * 1.5)
    readonly property real performancePointRadius: Math.max(2, borderWidth * 2)
    readonly property real minimumCpuChartScale: 10
    readonly property int footerExpandedWidth: Style.space(1120)
    readonly property int footerSidePadding: Style.space(10)
    readonly property int footerSpacing: Style.space(7)
    readonly property int outerGap: Style.gapsOut
    readonly property int borderWidth: Math.max(1, Style.normalBorderWidth)
    readonly property int dividerWidth: 1
    readonly property real dividerOpacity: 0.58
    readonly property real subtleDividerOpacity: 0.32
    readonly property real connectorOpacity: 0.42
    readonly property real disabledOpacity: 0.3
    readonly property real previewOpacity: 0.72
    readonly property int fastMotionDuration: 110
}
