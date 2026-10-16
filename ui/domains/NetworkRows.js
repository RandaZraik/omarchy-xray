.pragma library
.import "../Format.js" as Format

var scopes = {"internet": "Internet", "local": "Local network", "loopback": "This machine", "multicast": "Multicast", "listener": "Listening"}

function owners(row) {
    return (row.owners || []).map(function(owner) { return owner.name + " · " + owner.pid }).join(", ")
}

function endpoint(row) {
    return Format.addressPort(row.remoteAddress, row.remotePort)
}

function flowRows(network, search, scope, protocol, sort, includeClosed) {
    var needle = String(search || "").trim().toLowerCase()
    var rows = ((network || {}).flows || []).filter(function(row) {
        if (row.listening || !Number(row.remotePort)) return false
        if (!includeClosed && !row.active) return false
        if (scope && row.scope !== scope) return false
        if (protocol && String(row.protocol).indexOf(protocol) !== 0) return false
        return !needle || [owners(row), row.localAddress, row.localPort,
            row.remoteAddress, row.remotePort, row.hostname, row.protocol,
            row.state, scopes[row.scope]].join(" ").toLowerCase().indexOf(needle) >= 0
    })
    rows.sort(function(a, b) {
        if (sort === "recent") return Number(b.lastSeen) - Number(a.lastSeen) || String(a.id).localeCompare(String(b.id))
        var group = owners(a).localeCompare(owners(b))
        return group || (Number(b.sentRate || 0) + Number(b.receivedRate || 0))
            - (Number(a.sentRate || 0) + Number(a.receivedRate || 0)) || endpoint(a).localeCompare(endpoint(b))
    })
    return rows.map(function(row, index) {
        return Object.assign({}, row, {"ownerLabel": owners(row), "endpoint": endpoint(row),
            "scopeLabel": scopes[row.scope] || row.scope,
            "firstInGroup": index === 0 || owners(rows[index - 1]) !== owners(row),
            "lastInGroup": index === rows.length - 1 || owners(rows[index + 1]) !== owners(row)})
    })
}

function canInspect(owner, processes) {
    return (processes || []).some(function(row) {
        return Number(row.pid) === Number(owner.pid)
            && Number(row.startTime) === Number(owner.startTime)
            && Number(row.uid) === Number(owner.uid)
    })
}

function status(row) {
    if (!row.active) return "Last seen"
    if (row.sampleStatus === "baseline") return "Gathering a baseline"
    if (row.sampleStatus === "unavailable" || row.sampleStatus === "unknown") return "Rates unavailable"
    return row.state || "Observed"
}

function stats(network) {
    var totals = (network || {}).totals || {}
    var destinations = ({})
    ;((network || {}).flows || []).forEach(function(row) {
        if (row.active && !row.listening && Number(row.remotePort)) destinations[row.remoteAddress] = true
    })
    return [
        {"label": "UPLOAD", "value": Format.rate(totals.sentRate), "tone": "network"},
        {"label": "DOWNLOAD", "value": Format.rate(totals.receivedRate), "tone": "device"},
        {"label": "DESTINATIONS", "value": String(Object.keys(destinations).length), "tone": "network"},
        {"label": "RATES AVAILABLE", "value": Number(totals.measuredFlows || 0) + " of " + Number(totals.activeFlows || 0), "detail": "connections", "tone": "storage"}
    ]
}

function timestamp(seconds) {
    return seconds ? new Date(Number(seconds) * 1000).toLocaleTimeString(Qt.locale(), "HH:mm:ss") : "—"
}

function flowFacts(row) {
    var measured = row.sampleStatus === "measured" || Number(row.sampleSeconds) > 0
        || Number(row.sentBytes) > 0 || Number(row.receivedBytes) > 0
    var rows = [
        {"label": "Destination", "value": endpoint(row)},
        {"label": "Process", "value": owners(row)},
        {"label": "Transferred", "value": measured
            ? "↑ " + Format.bytes(row.sentBytes) + "   ↓ " + Format.bytes(row.receivedBytes)
            : "Not measured", "tone": measured ? "network" : "storage"}
    ]
    if (row.hostname) rows.splice(1, 0, {"label": "Name hint", "value": row.hostname})
    return rows
}

function flowDetails(network, row) {
    var rows = [
        {"label": "Local address", "value": Format.addressPort(row.localAddress, row.localPort)},
        {"label": "State", "value": row.protocol + " · " + status(row)},
        {"label": "Seen", "value": timestamp(row.firstSeen) + " – " + timestamp(row.lastSeen)},
        {"label": "Byte count", "value": network.mode === "packets"
            ? "IP headers + data; retransmitted packets count again."
            : "TCP data only; uploads count when acknowledged."},
        {"label": "Socket", "value": String(row.inode) + " · " + row.networkNamespace}
    ]
    if (row.rttMs !== undefined) rows.push({"label": "TCP delay", "value": Format.number(row.rttMs, 2) + " ms · " + Number(row.retransmits || 0) + " retransmissions since the socket opened"})
    if ((row.owners || []).length > 1) rows.push({"label": "Shared socket", "value": "Counted once. Traffic cannot be split between owners."})
    if (row.hostname) rows.push({"label": "Name source", "value": "Reverse DNS; may not identify the website requested."})
    return rows
}

function coverageFacts(network) {
    var flows = (network.flows || []).filter(function(row) { return row.active && !row.listening })
    return ["TCP", "UDP"].map(function(protocol) {
        var rows = flows.filter(function(row) { return String(row.protocol).indexOf(protocol) === 0 })
        var measured = rows.filter(function(row) { return row.sampleStatus === "measured" }).length
        var baseline = rows.some(function(row) { return row.sampleStatus === "baseline" })
        var value = !rows.length ? "No connections observed"
            : protocol === "UDP" && network.mode !== "packets" ? "Not measured · needs packet capture"
            : baseline && !measured ? "Waiting for the next sample"
            : measured + " of " + rows.length + " connections measured"
        return {"label": protocol + " rates", "value": value,
            "tone": measured === rows.length ? "network" : "storage"}
    })
}

function coverageDetails(network) {
    var capture = network.capture || {}
    var rows = [
        {"label": "Sampling", "value": "Very short connections can be missed between samples."},
        {"label": "Shared sockets", "value": "Counted once. Ambiguous owners are left unassigned."},
        {"label": "Destinations", "value": "An IP address does not identify a website."}
    ]
    if (network.mode === "packets") {
        rows.push({"label": "Capture", "value": capture.interface + " · current network namespace only"})
        rows.push({"label": "Unassigned", "value": Number(network.unattributedPackets || 0) + " packets this sample; may belong to other apps"})
        rows.push({"label": "Dropped", "value": capture.droppedPackets === null ? "Not reported by capture source" : String(capture.droppedPackets || 0)})
        rows.push({"label": "Skipped", "value": Number(capture.skippedPackets || 0) + " unsupported packets · " + Number(capture.overflowPackets || 0) + " over the capture limit"})
    }
    if (network.historyTruncated || network.omittedFlows)
        rows.push({"label": "History", "value": "Some entries were omitted to keep recording bounded."})
    ;(network.limited || []).forEach(function(message) {
        if (message === "UDP traffic rates need packet capture") return
        rows.push({"label": "Unavailable", "value": String(message), "tone": "storage"})
    })
    return rows
}

function captureStatus(capture) {
    if (capture.starting) return "Starting…"
    if (capture.active) return "On · " + capture.interface
    if (capture.errorKind === "missing-helper") return "Install dumpcap with capture permission, then retry."
    if (capture.errorKind === "helper-launch") return "Could not start dumpcap · see error details."
    if (capture.errorKind === "interface-unavailable") return "Choose an available interface, then retry."
    if (capture.error) return "Capture failed · see error details."
    return "Off · requires capture permission"
}
