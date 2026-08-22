import QtQuick
import qs.Ui
import "../Format.js" as Format

Button {
    property string iconName: ""

    iconText: Format.icon(iconName)
    bordered: true
    focusable: true
    horizontalPadding: 10
    verticalPadding: 7
}

