.pragma library
.import "Format.js" as Format

function unavailableRow(icon, title) {
    return {"icon": icon, "title": title, "subtitle": "Information unavailable", "meta": "UNAVAILABLE", "active": false, "limited": true}
}

function stateOf(availability, name) {
    var value = availability[name]
    if (value === false || value === "unavailable") return "unavailable"
    if (value === "partial") return "partial"
    return "available"
}

function coverageRows(devices) {
    var availability = (devices || {}).availability || {}
    return Object.keys(availability).sort().map(function(name) {
        return {"name": name, "state": stateOf(availability, name)}
    }).filter(function(row) {
        return row.state !== "available"
    }).map(function(row) {
        return {
            "title": row.name,
            "subtitle": row.state === "partial"
                ? "Some clients could not be inspected for the selected tree"
                : "This information was unavailable for the selected app",
            "meta": row.state.toUpperCase()
        }
    })
}

function withCoverage(row, state) {
    if (state !== "partial") return row
    return Object.assign({}, row, {
        "subtitle": row.active ? row.subtitle + " · partial" : "No detected client · partial",
        "meta": row.active ? row.meta : "PARTIAL",
        "limited": true
    })
}

function pipewireRow(pipewire, kind, label, state) {
    if (state === "unavailable") return unavailableRow(kind, label)
    var matches = pipewire.filter(function(row) { return row.kind === kind && row.active === true })
    if (!matches.length)
        return withCoverage({"icon": kind, "title": label, "subtitle": "Not in use", "meta": "", "active": false}, state)
    var match = matches[0]
    var owner = match.application || match.name || "PipeWire"
    return withCoverage({
        "icon": kind,
        "title": label,
        "subtitle": owner + (matches.length > 1 ? " +" + (matches.length - 1) : ""),
        "meta": matches.length + " LIVE",
        "active": true
    }, state)
}

function gpuRow(gpu, state) {
    if (state === "unavailable") return unavailableRow("gpu", "GPU")
    if (!gpu.length)
        return withCoverage({"icon": "gpu", "title": "GPU", "subtitle": "Not in use", "meta": "", "active": false}, state)
    return withCoverage({
        "icon": "gpu",
        "title": "GPU",
        "subtitle": Format.basename(gpu[0].device) + (gpu.length > 1 ? " +" + (gpu.length - 1) : ""),
        "meta": gpu.length + " LIVE",
        "active": true
    }, state)
}

function inhibitorRow(inhibitors, state) {
    if (state === "unavailable") return unavailableRow("sleep", "Sleep inhibition")
    if (!inhibitors.length)
        return withCoverage({"icon": "sleep", "title": "Sleep inhibition", "subtitle": "Not in use", "meta": "", "active": false}, state)
    return withCoverage({
        "icon": "sleep",
        "title": "Sleep inhibition",
        "subtitle": String(inhibitors[0].who || inhibitors[0].what || "Application") + (inhibitors.length > 1 ? " +" + (inhibitors.length - 1) : ""),
        "meta": inhibitors.length + " LIVE",
        "active": true
    }, state)
}

function summarize(devices) {
    var source = devices || {}
    var pipewire = source.pipewire || []
    var gpu = source.gpu || []
    var inhibitors = source.inhibitors || []
    var availability = source.availability || {}
    var states = {
        "pipewire": stateOf(availability, "pipewire"),
        "gpu": stateOf(availability, "gpu"),
        "inhibitors": stateOf(availability, "inhibitors")
    }
    var limitedSources = Object.keys(availability).filter(function(name) {
        return stateOf(availability, name) !== "available"
    })
    var rows = [
        pipewireRow(pipewire, "microphone", "Microphone", states.pipewire),
        pipewireRow(pipewire, "camera", "Camera", states.pipewire),
        pipewireRow(pipewire, "screen", "Screen capture", states.pipewire),
        pipewireRow(pipewire, "audio", "Audio playback", states.pipewire),
        pipewireRow(pipewire, "audio-capture", "Audio capture", states.pipewire),
        pipewireRow(pipewire, "video", "Video capture", states.pipewire),
        gpuRow(gpu, states.gpu),
        inhibitorRow(inhibitors, states.inhibitors)
    ]
    return {
        "rows": rows,
        "activeRows": rows.filter(function(row) { return row.active === true }),
        "limitedSources": limitedSources
    }
}
