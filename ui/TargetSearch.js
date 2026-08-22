.pragma library
.import "Format.js" as Format

function score(value, needle) {
    var text = String(value || "").toLowerCase()
    if (text === needle) return 100
    if (text.startsWith(needle)) return 70
    if (text.indexOf(needle) >= 0) return 40
    return 0
}

function add(result, needle, kind, title, subtitle, query, searchable, boost) {
    var matchScore = score(searchable, needle)
    if (matchScore > 0)
        result.push({"kind": kind, "title": title, "subtitle": subtitle, "query": query, "rank": matchScore + Number(boost || 0)})
}

function matches(query, catalog, limit) {
    var needle = String(query || "").trim().toLowerCase()
    if (!needle) return []
    var source = catalog || {}
    var result = []
    ;(source.windows || []).forEach(function(window) {
        var title = window.class || "Application"
        var subtitle = window.title || "PID " + window.pid
        add(result, needle, "window", title, subtitle, "window:" + window.address,
            title + " " + subtitle + " " + window.pid + " " + window.address, window.focused ? 12 : 8)
    })
    ;(source.processes || []).forEach(function(process) {
        add(result, needle, "process", process.name || "Process", "PID " + process.pid,
            "pid:" + process.pid, (process.name || "") + " " + process.pid, 4)
    })
    ;(source.services || []).forEach(function(service) {
        add(result, needle, "service", service.id || "Service",
            (service.scope || "") + " · " + (service.description || "Running unit"),
            "service:" + (service.scope ? service.scope + ":" : "") + service.id,
            (service.id || "") + " " + (service.description || "") + " " + (service.scope || ""), 6)
    })
    ;(source.containers || []).forEach(function(container) {
        add(result, needle, "container", container.name || container.shortId || "Container",
            (container.runtime || "container") + " · " + (container.image || container.status || "running"),
            "container:" + (container.runtime ? container.runtime + ":" : "") + (container.id || container.name),
            (container.name || "") + " " + (container.id || "") + " " + (container.image || "") + " " + (container.composeProject || ""), 6)
    })
    ;(source.devices || []).forEach(function(device) {
        var owner = device.application || device.name || device.kind + " client"
        add(result, needle, "device", owner,
            (device.kind || "device") + " · PID " + device.pid,
            "pid:" + device.pid,
            owner + " " + (device.kind || "") + " " + (device.name || "") + " " + device.pid, 5)
    })
    ;(source.gpu || []).forEach(function(client) {
        add(result, needle, "gpu", client.application || "GPU client", "PID " + client.pid + " · " + Format.basename(client.device),
            "pid:" + client.pid, (client.application || "") + " gpu " + client.pid, 5)
    })
    ;(source.ports || []).forEach(function(port) {
        add(result, needle, "port", "Port " + port.localPort,
            (port.protocol || "") + " · " + (port.state || "listening"),
            ":" + port.localPort, String(port.localPort), 3)
    })
    result.sort(function(left, right) {
        return right.rank - left.rank || left.title.localeCompare(right.title) || left.subtitle.localeCompare(right.subtitle)
    })
    return result.slice(0, Math.max(1, Number(limit || 7)))
}
