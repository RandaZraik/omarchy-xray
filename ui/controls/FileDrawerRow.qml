import QtQuick
import "../Format.js" as Format

EvidenceDrawerRow {
    id: root

    required property var row
    readonly property bool attention: row.deleted === true || row.rowType === "lock"

    rowHeight: theme.drawerResourceRowHeight
    title: String(row.title || "")
    subtitle: String(row.subtitle || "")
    detail: String(row.detail || "")
    meta: String(row.meta || "")
    iconText: Format.icon(row.rowType === "lock" ? "lock" : row.icon || "file")
    contentColor: attention ? theme.danger : accentColor
    showRail: attention
    emphasized: attention
    titleElide: Text.ElideMiddle
}
