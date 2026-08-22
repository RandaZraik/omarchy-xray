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
        return {
            title: Format.endpoint(row),
            subtitle: row.protocol + " · " + row.state,
            meta: row.publicListener ? "ALL INTERFACES" : (row.listening ? "LISTENER" : "")
        }
    })
}

function files(snapshot) {
    var rows = (snapshot.files || []).map(function(row) {
        return {
            title: row.target || "Descriptor",
            subtitle: "PID " + row.pid + " · FD " + row.fd + " · " + (row.mode || row.kind),
            meta: row.deleted ? "DELETED, STILL OPEN" : ""
        }
    })
    ;(snapshot.locks || []).forEach(function(row) {
        rows.push({
            title: "Kernel file lock",
            subtitle: (row.owner || "PID " + row.pid) + " · inode " + row.inode + " · " + (row.type || "lock"),
            meta: row.mode || "LOCKED"
        })
    })
    return rows
}

function devices(snapshot) {
    var evidence = snapshot.devices || {}
    var rows = (evidence.pipewire || []).concat(evidence.gpu || [])
        .concat(evidence.inhibitors || []).map(function(row) {
            if (row.device) return {
                title: row.device,
                subtitle: "GPU client " + row.clientId + " · PID " + row.pid,
                meta: Format.percent(row.utilizationPercent)
            }
            if (row.what) return {
                title: row.what + " inhibitor",
                subtitle: row.why || row.who,
                meta: row.mode || ""
            }
            return {
                title: row.name || row.kind,
                subtitle: (row.application || "PipeWire") + " · PID " + row.pid,
                meta: row.active ? "ACTIVE" : row.state
            }
        })
    return rows.concat(DeviceSummary.coverageRows(evidence))
}
