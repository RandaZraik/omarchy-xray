import QtQuick
import "../Format.js" as Format

EvidenceDrawerRow {
    id: root

    required property var row

    rowHeight: theme.drawerConnectionRowHeight
    title: String(row.title || "")
    subtitle: String(row.subtitle || "")
    detail: String(row.detail || "")
    meta: String(row.meta || "")
    iconText: Format.icon(String(row.icon || "device"))
    contentColor: row.limited === true ? theme.storageAccent
        : row.active === true ? accentColor : theme.muted
    iconHighlighted: row.active === true
    emphasized: row.active === true
}
