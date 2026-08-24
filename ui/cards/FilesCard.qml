import QtQuick
import "../controls"
import "../Format.js" as Format
import "../DetailDomains.js" as DetailDomains

Card {
    id: root
    objectName: "xrayFilesCard"

    property var snapshot: ({})
    readonly property var rows: snapshot.files || []
    readonly property var locks: snapshot.locks || []
    function rowScore(row) {
        if (row.deleted) return 0;
        if (["file", "directory", "device", "pty"].indexOf(row.kind) >= 0) return 1;
        if (String(row.target || "").startsWith("/")) return 2;
        return 3;
    }
    function compareRows(left, right) {
        return root.rowScore(left) - root.rowScore(right)
            || Number(left.fd || 0) - Number(right.fd || 0);
    }
    function preferredRows(source, limit) {
        var selected = [];
        for (var index = 0; index < source.length; index++) {
            var candidate = source[index];
            var low = 0;
            var high = selected.length;
            while (low < high) {
                var middle = Math.floor((low + high) / 2);
                if (root.compareRows(selected[middle], candidate) <= 0)
                    low = middle + 1;
                else
                    high = middle;
            }
            if (low >= limit) continue;
            selected.splice(low, 0, candidate);
            if (selected.length > limit) selected.pop();
        }
        return selected;
    }
    readonly property var displayRows: preferredRows(rows, 16)
    signal detailsRequested()
    title: DetailDomains.title(DetailDomains.Files)
    accentColor: theme.storageAccent
    countText: rows.length + " DESCRIPTORS · " + locks.length + " LOCKS"
    detailsCount: DetailDomains.count(DetailDomains.Files, snapshot)
    interactive: true
    onClicked: detailsRequested()

    body: Column {
        anchors.fill: parent
        spacing: 0

        EvidenceTableHeader {
            width: parent.width
            theme: root.theme
            columns: [
                {"text": "FD", "width": 0.08},
                {"text": "PATH / ENDPOINT", "width": 0.64},
                {"text": "KIND", "width": 0.14},
                {"text": "ACCESS", "width": 0.14}
            ]
        }

        Repeater {
            model: root.displayRows.slice(0, Math.max(0, Math.floor(
                (parent.height - root.theme.evidenceHeaderHeight)
                    / root.theme.evidenceRowHeight
            )))
            delegate: EvidenceTableRow {
                required property var modelData
                width: parent.width
                theme: root.theme
                cells: [
                    {"width": 0.08, "text": modelData.fd === undefined || modelData.fd === null ? "" : String(modelData.fd), "color": root.theme.muted},
                    {"width": 0.64, "text": modelData.target || "Descriptor", "color": modelData.deleted ? root.theme.danger : root.theme.text, "elide": Text.ElideMiddle},
                    {"width": 0.14, "text": modelData.kind || "", "color": root.theme.muted},
                    {"width": 0.14, "text": modelData.deleted ? "DELETED" : String(modelData.mode || ""), "color": modelData.deleted ? root.theme.danger : root.accentColor, "fontSize": root.theme.microFontSize}
                ]
            }
        }
    }
}
