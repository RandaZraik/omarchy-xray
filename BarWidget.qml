import QtQuick
import qs.Ui
import "ui"
import "ui/Format.js" as Format

BarWidget {
    id: root
    objectName: "xrayBarWidget"

    XRayContract { id: contract }
    XRayTheme { id: theme }

    moduleName: contract.pluginId
    implicitWidth: launcher.implicitWidth
    implicitHeight: launcher.implicitHeight

    BarIconButton {
        id: launcher
        objectName: "xrayBarLauncher"

        anchors.fill: parent
        bar: root.bar
        text: Format.icon("xray")
        fontFamily: theme.dataFont
        tooltipText: "Trace system activity"
        onPressed: function(button) {
            if (!root.bar || !root.bar.shell)
                return;
            root.bar.shell.toggle(root.moduleName, "{}")
        }
    }
}
