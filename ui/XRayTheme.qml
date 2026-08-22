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
    readonly property real semanticSaturationScale: 0.9
    readonly property real minimumSemanticValue: 0.72
    readonly property real neutralAccentTextMix: 0.3
    readonly property color cpuAccent: accent
    readonly property color processAccent: semanticAccent(processHueOffset)
    readonly property color memoryAccent: semanticAccent(memoryHueOffset)
    readonly property color networkAccent: semanticAccent(networkHueOffset)
    readonly property color storageAccent: semanticAccent(storageHueOffset)
    readonly property color deviceAccent: networkAccent
    readonly property color alertAccent: danger

    readonly property real mutedTextMix: 0.68
    readonly property real quietSurfaceMix: 0.1
    readonly property real raisedSurfaceMix: 0.14
    readonly property real previewSurfaceMix: 0.045
    readonly property real tintedSurfaceMix: 0.09
    readonly property real dangerSurfaceMix: 0.08
    readonly property real cardBorderTextMix: 0.34
    readonly property real accentBorderMix: 0.48
    readonly property real strongAccentBorderMix: 0.78
    readonly property real sectionAccentMix: 0.22
    readonly property real metricAccentMix: 0.46
    readonly property real gridAccentMix: 0.24
    readonly property real hoverBorderMix: 0.32
    readonly property real headingAccentMix: 0.34
    readonly property color muted: blend(panel, text, mutedTextMix)
    readonly property color quietSurface: blend(panel, text, quietSurfaceMix)
    readonly property color raisedSurface: blend(quietSurface, accent, raisedSurfaceMix)
    readonly property color previewSurface: blend(quietSurface, accent, previewSurfaceMix)
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
    readonly property int outerGap: Style.gapsOut
    readonly property int borderWidth: Math.max(1, Style.normalBorderWidth)
    readonly property int dividerWidth: 1
    readonly property real dividerOpacity: 0.42
    readonly property real subtleDividerOpacity: 0.46
    readonly property real connectorOpacity: 0.55
    readonly property real disabledOpacity: 0.3
    readonly property real previewOpacity: 0.72
    readonly property int fastMotionDuration: 110
}
