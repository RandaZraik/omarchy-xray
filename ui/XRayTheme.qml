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

    function semanticAccent(turns) {
        if (accent.hsvSaturation < minimumAccentSaturation)
            return blend(accent, text, neutralAccentTextMix);
        var hue = (accent.hsvHue + turns) % 1;
        return Qt.hsva(
            hue < 0 ? hue + 1 : hue,
            Math.min(1, accent.hsvSaturation * semanticSaturationScale),
            Math.max(minimumSemanticValue, accent.hsvValue),
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

    readonly property color canvas: Color.background
    readonly property color panel: Color.background
    readonly property color text: Color.menu.text
    readonly property color accent: Color.accent
    readonly property color danger: Color.urgent
    readonly property color border: Color.menu.border
    readonly property color selected: Color.menu.selectedBackground
    readonly property color scrim: Color.menu.scrim
    readonly property color transparent: withAlpha(panel, 0)

    // Omarchy provides the foundation. X-Ray rotates that live accent into a
    // compact semantic spectrum, keeping every theme coherent without owning
    // a second hardcoded palette.
    readonly property real processHueOffset: 0.1
    readonly property real memoryHueOffset: -0.35
    readonly property real networkHueOffset: -0.11
    readonly property real storageHueOffset: 0.48
    readonly property real minimumAccentSaturation: 0.18
    readonly property real semanticSaturationScale: 1.15
    readonly property real minimumSemanticValue: 0.8
    readonly property real neutralAccentTextMix: 0.3
    readonly property color cpuAccent: accent
    readonly property color processAccent: semanticAccent(processHueOffset)
    readonly property color memoryAccent: semanticAccent(memoryHueOffset)
    readonly property color networkAccent: semanticAccent(networkHueOffset)
    readonly property color storageAccent: semanticAccent(storageHueOffset)
    readonly property color deviceAccent: networkAccent
    readonly property color alertAccent: danger

    // Surface depth is derived from Omarchy's active background, foreground,
    // and accent. The dashboard stays calm while cards, navigation, and the
    // selected-target strip remain visually distinct in both dark and light
    // themes.
    readonly property real mutedTextMix: 0.55
    readonly property real quietSurfaceMix: 0.065
    readonly property real browserSurfaceMix: 0.025
    readonly property real raisedSurfaceMix: 0.14
    readonly property real previewSurfaceMix: 0.055
    readonly property real controlFocusSurfaceMix: 0.07
    readonly property real controlFocusBorderMix: 0.32
    readonly property real controlActiveSurfaceMix: 0.095
    readonly property real controlHoverSurfaceMix: 0.06
    readonly property real tintedSurfaceMix: 0.12
    readonly property real dangerSurfaceMix: 0.1
    readonly property real cardBorderTextMix: 0.4
    readonly property real accentBorderMix: 0.48
    readonly property real strongAccentBorderMix: 0.78
    readonly property real sectionAccentMix: 0.58
    readonly property real metricAccentMix: 0.72
    readonly property real gridAccentMix: 0.42
    readonly property real hoverBorderMix: 0.44
    readonly property real headingAccentMix: 0.64
    readonly property color muted: blend(Color.muted, text, mutedTextMix)
    readonly property color quietSurface: blend(panel, text, quietSurfaceMix)
    readonly property color browserSurface: blend(panel, accent, browserSurfaceMix)
    readonly property color summarySurface: previewSurface
    readonly property color raisedSurface: blend(quietSurface, accent, raisedSurfaceMix)
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
    readonly property color strongAccentBorder: blend(border, accent, strongAccentBorderMix)
    readonly property color sectionText: blend(text, accent, sectionAccentMix)
    readonly property color metricText: blend(text, accent, metricAccentMix)
    readonly property color grid: blend(panel, accent, gridAccentMix)
    readonly property color drawerScrim: withAlpha(canvas, 0.46)
    readonly property color busyScrim: withAlpha(panel, 0.82)
    readonly property color confirmationScrim: withAlpha(canvas, 0.76)
    readonly property color trace: cpuAccent
    readonly property color secondaryTrace: memoryAccent

    readonly property string bodyFont: Style.font.family
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
    readonly property int radius: Math.max(4, Style.cornerRadius)
    readonly property int gap: Style.space(8)
    readonly property int smallGap: Style.space(5)
    readonly property int pad: Style.space(10)
    readonly property int panelPadding: Style.space(16)
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
    readonly property int targetBrowserTabIndicatorHeight: Math.max(2, borderWidth * 2)
    readonly property int targetBrowserBeamWidth: Math.max(2, borderWidth * 2)
    readonly property int telemetryHeight: Style.space(72)
    readonly property int telemetryTargetWidth: Style.space(340)
    readonly property int telemetryTargetMinimumWidth: Style.space(240)
    readonly property int telemetryMetricWidth: Style.space(132)
    readonly property int telemetryMetricMinimumWidth: Style.space(86)
    readonly property int telemetryModulePadding: Style.space(10)
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
    readonly property int footerSidePadding: Style.space(8)
    readonly property int footerSpacing: Style.space(6)
    readonly property int outerGap: Style.gapsOut
    readonly property int borderWidth: Math.max(1, Style.normalBorderWidth)
    readonly property int dividerWidth: 1
    readonly property real dividerOpacity: 0.78
    readonly property real subtleDividerOpacity: 0.56
    readonly property real connectorOpacity: 0.55
    readonly property real disabledOpacity: 0.3
    readonly property real previewOpacity: 0.72
    readonly property int fastMotionDuration: 110
}
