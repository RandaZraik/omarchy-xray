.pragma library
.import "../Format.js" as Format
.import "../DeviceSummary.js" as DeviceSummary

function processCount(snapshot) {
    return (snapshot.processes || []).length
}

function connectionCount(snapshot) {
    return (snapshot.connections || []).length
}

function fileCount(snapshot) {
    return (snapshot.files || []).length + (snapshot.locks || []).length
}

function deviceCount(snapshot) {
    var devices = snapshot.devices || {}
    return (devices.pipewire || []).length + (devices.gpu || []).length
        + (devices.inhibitors || []).length + DeviceSummary.coverageRows(devices).length
}

function processes(snapshot) {
    return (snapshot.processes || []).map(function(row) {
        return {
            title: row.name || "Process",
            subtitle: "PID " + row.pid + " · " + Format.firstCommand(row.command),
            meta: Format.percent(row.cpuPercent) + " · " + Format.bytes(row.memoryBytes),
            pid: row.pid
        }
    })
}

function connections(snapshot) {
    return (snapshot.connections || []).map(function(row) {
        var pids = row.pids || []
        var remote = Number(row.remotePort || 0)
            ? Format.addressPort(row.remoteAddress, row.remotePort) : ""
        return {
            rowType: "connection",
            section: row.publicListener || row.externallyReachable
                ? "exposed"
                : row.listening ? "listeners"
                : closingState(row.state) ? "closing" : "active",
            title: Format.addressPort(row.localAddress, row.localPort),
            remote: remote,
            subtitle: (pids.length ? "PID " + pids.join(", ") : "Owner unavailable")
                + " · inode " + (row.inode === undefined ? "unknown" : row.inode)
                + (row.networkNamespace ? " · " + row.networkNamespace : ""),
            meta: row.publicListener ? "ALL INTERFACES"
                : row.externallyReachable && row.listening ? "NETWORK LISTENER"
                : row.listening ? "LISTEN" : String(row.state || "OPEN").toUpperCase(),
            protocol: row.protocol || "",
            state: row.state || "",
            listening: row.listening === true,
            exposed: row.publicListener === true || row.externallyReachable === true,
            publicListener: row.publicListener === true,
            pids: pids,
            inode: row.inode,
            networkNamespace: row.networkNamespace || "",
            searchText: [row.protocol, row.state, row.localAddress, row.localPort,
                row.remoteAddress, row.remotePort, row.inode,
                row.networkNamespace].concat(pids).join(" ")
        }
    })
}

function closingState(state) {
    return ["Fin wait 1", "Fin wait 2", "Time wait", "Closed", "Close wait",
        "Last ack", "Closing"].indexOf(String(state || "")) >= 0
}

function files(snapshot) {
    var rows = (snapshot.files || []).map(function(row) {
        return {
            rowType: "file",
            section: fileSection(row),
            title: row.target || "Descriptor",
            subtitle: "PID " + row.pid + " · FD " + row.fd + " · " + (row.mode || row.kind),
            meta: row.deleted ? "DELETED, STILL OPEN" : "",
            pid: row.pid,
            fd: row.fd,
            target: row.target || "Descriptor",
            kind: row.kind || "file",
            mode: row.mode || "unknown",
            deleted: row.deleted === true,
            position: row.position,
            flags: row.flags,
            mountId: row.mountId,
            searchText: [row.target, row.pid, row.fd, row.kind, row.mode,
                row.position, row.flags, row.mountId].join(" ")
        }
    })
    ;(snapshot.locks || []).forEach(function(row) {
        rows.push({
            rowType: "lock",
            section: "attention",
            title: "Kernel file lock",
            subtitle: (row.owner || "PID " + row.pid) + " · "
                + (row.type || "lock") + " " + (row.mode || "")
                + " · bytes " + row.start + "–" + row.end,
            detail: "inode " + row.inode + " · lock " + row.id
                + (row.scope ? " · " + row.scope : ""),
            meta: row.mode || "LOCKED",
            pid: row.pid,
            lockId: row.id,
            kind: row.type || "lock",
            mode: row.mode || "",
            owner: row.owner || "PID " + row.pid,
            inode: row.inode,
            start: row.start,
            end: row.end,
            scope: row.scope || "",
            searchText: [row.owner, row.pid, row.id, row.type, row.mode,
                row.inode, row.start, row.end, row.scope].join(" ")
        })
    })
    return rows
}

function unique(values) {
    var seen = ({})
    var result = []
    ;(values || []).forEach(function(value) {
        var key = String(value)
        if (value === undefined || value === null || key === "" || seen[key]) return
        seen[key] = true
        result.push(value)
    })
    return result
}

function fileIcon(section) {
    var icons = {
        "attention": "warning", "files": "file", "devices": "device",
        "memory": "memory", "sockets": "socket", "pipes": "pipe",
        "events": "event", "other": "file"
    }
    return icons[section] || "file"
}

function aggregateFiles(values) {
    var result = []
    var byKey = ({})
    ;(values || []).forEach(function(row) {
        if (row.rowType === "lock") {
            result.push(Object.assign({}, row, {"sourceCount": 1}))
            return
        }
        var key = JSON.stringify([row.section, row.target, row.kind, row.mode,
            row.deleted === true])
        var aggregate = byKey[key]
        if (!aggregate) {
            aggregate = {
                "rowType": "fileGroup",
                "section": row.section,
                "title": row.target,
                "target": row.target,
                "kind": row.kind,
                "mode": row.mode,
                "deleted": row.deleted === true,
                "icon": fileIcon(row.section),
                "sourceCount": 0,
                "pids": [], "fds": [], "positions": [], "flags": [], "mountIds": [],
                "searchParts": []
            }
            byKey[key] = aggregate
            result.push(aggregate)
        }
        aggregate.sourceCount++
        aggregate.pids.push(row.pid)
        aggregate.fds.push(row.fd)
        aggregate.positions.push(row.position)
        aggregate.flags.push(row.flags)
        aggregate.mountIds.push(row.mountId)
        aggregate.searchParts.push(row.searchText)
    })
    result.forEach(function(row) {
        if (row.rowType !== "fileGroup") return
        row.pids = unique(row.pids)
        row.fds = unique(row.fds)
        row.positions = unique(row.positions)
        row.flags = unique(row.flags)
        row.mountIds = unique(row.mountIds)
        row.subtitle = row.sourceCount + (row.sourceCount === 1
            ? " descriptor" : " descriptors")
            + " · PID " + row.pids.join(", ") + " · FD " + row.fds.join(", ")
        var details = [row.mode]
        if (row.mountIds.length) details.push("mount " + row.mountIds.join(", "))
        if (row.flags.length) details.push("flags " + row.flags.join(", "))
        if (row.positions.length) details.push("offset " + row.positions.join(", "))
        row.detail = details.join(" · ")
        row.meta = row.deleted ? "DELETED"
            : row.sourceCount > 1 ? row.sourceCount + " FDS" : "FD " + row.fds[0]
        row.searchText = row.searchParts.join(" ")
    })
    return result
}

function fileSection(row) {
    var target = String(row.target || "")
    if (row.deleted) return "attention"
    if (target.indexOf("anon_inode:") === 0) return "events"
    if (target.indexOf("socket:[") === 0) return "sockets"
    if (target.indexOf("pipe:[") === 0) return "pipes"
    if (target.indexOf("/dev/") === 0) return "devices"
    if (target.indexOf("memfd:") === 0 || target.indexOf("/dev/shm/") === 0)
        return "memory"
    if (target.indexOf("/") === 0) return "files"
    return "other"
}

function devices(snapshot) {
    var evidence = snapshot.devices || {}
    var rows = (evidence.pipewire || []).map(function(row) {
        return {
            rowType: "device",
            section: "media",
            icon: row.kind && row.kind !== "other" ? row.kind : "device",
            kind: row.kind || "pipewire",
            title: row.name || row.kind || "PipeWire stream",
            subtitle: (row.application || "PipeWire") + " · PID " + row.pid,
            detail: [row.mediaClass, row.role, row.source,
                row.id !== undefined ? "node " + row.id : ""].filter(Boolean).join(" · "),
            meta: row.active ? "ACTIVE" : row.state,
            active: row.active === true,
            searchText: [row.name, row.application, row.pid, row.mediaClass,
                row.role, row.source, (row.sourceIds || []).join(" "), row.id,
                row.state].join(" ")
        }
    })
    ;(evidence.gpu || []).forEach(function(row) {
        rows.push({
            icon: "gpu",
            kind: "gpu",
            rowType: "device",
            section: "gpu",
            title: "GPU client" + (row.clientId !== undefined
                ? " " + row.clientId : ""),
            subtitle: Format.basename(row.device || "GPU") + " · PID " + row.pid,
            detail: (row.memoryBytes !== undefined
                    ? Format.bytes(row.memoryBytes) + " " + (row.memoryKind || "memory")
                    : "Memory unavailable")
                + (Object.keys(row.engines || {}).length
                    ? " · " + Object.keys(row.engines || {}).join(", ") : ""),
            meta: Format.percent(row.utilizationPercent),
            active: true,
            searchText: [row.clientId, row.device, row.pid, row.memoryBytes,
                row.memoryKind, Object.keys(row.engines || {}).join(" ")].join(" ")
        })
    })
    ;(evidence.inhibitors || []).forEach(function(row) {
        rows.push({
            icon: "sleep",
            kind: "inhibitor",
            rowType: "device",
            section: "power",
            title: (row.what || "Sleep") + " inhibitor",
            subtitle: (row.who || "Application") + " · PID " + row.pid,
            detail: row.why || row.what || "Sleep is being inhibited",
            meta: row.mode || "ACTIVE",
            active: true,
            searchText: [row.what, row.who, row.why, row.mode, row.pid].join(" ")
        })
    })
    var activeRows = rows.filter(function(row) { return row.active === true })
    var inactiveRows = rows.filter(function(row) { return row.active !== true })
    var coverageRows = DeviceSummary.coverageRows(evidence).map(function(row) {
        var icons = {"gpu": "gpu", "inhibitors": "sleep", "pipewire": "audio"}
        var labels = {
            "gpu": "GPU inspection",
            "inhibitors": "Sleep inhibition",
            "pipewire": "Media inspection"
        }
        return Object.assign({}, row, {
            icon: icons[row.title] || "device",
            kind: "coverage",
            section: "availability",
            title: labels[row.title] || row.title,
            active: false,
            limited: true
        })
    })
    return activeRows.concat(inactiveRows, coverageRows)
}
