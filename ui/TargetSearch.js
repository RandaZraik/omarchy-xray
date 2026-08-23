.pragma library
.import "Format.js" as Format

var Filters = [
    {"id": "all", "label": "ALL", "kinds": []},
    {"id": "apps", "label": "APPS", "kinds": ["window"]},
    {"id": "processes", "label": "PROC", "kinds": ["process"]},
    {"id": "ports", "label": "PORTS", "kinds": ["port"]},
    {"id": "system", "label": "SYS", "kinds": ["service", "container", "device", "gpu"]}
]

var Groups = {
    "quick": {"rank": 0, "label": "QUICK INSPECT"},
    "window": {"rank": 1, "label": "OPEN APPS"},
    "device": {"rank": 2, "label": "ACTIVE DEVICES"},
    "gpu": {"rank": 2, "label": "ACTIVE DEVICES"},
    "port": {"rank": 3, "label": "LISTENING PORTS"},
    "container": {"rank": 4, "label": "CONTAINERS"},
    "service": {"rank": 5, "label": "SERVICES"},
    "process": {"rank": 6, "label": "PROCESSES"}
}

function score(value, needle) {
    var text = String(value || "").toLowerCase()
    if (text === needle) return 100
    if (text.startsWith(needle)) return 70
    if (text.indexOf(needle) >= 0) return 40
    return 0
}

function entry(kind, title, subtitle, query, searchable, boost) {
    var visibleText = String(title || "") + " " + String(subtitle || "")
    return {
        "kind": kind,
        "title": title,
        "subtitle": subtitle,
        "query": query,
        "searchable": visibleText + " " + String(searchable || "") + " " + query,
        "boost": Number(boost || 0)
    }
}

function entries(catalog) {
    var source = catalog || {}
    var result = []
    ;(source.quickTargets || []).forEach(function(target) {
        result.push(entry("quick", target.label || "Device activity",
            "Inspect active owners", target.query || "",
            (target.label || "") + " " + (target.query || ""), 10))
    })
    ;(source.windows || []).forEach(function(window) {
        var title = window.class || "Application"
        var subtitle = window.title || "PID " + window.pid
        result.push(entry("window", title, subtitle, window.query || "",
            title + " " + subtitle + " " + window.pid + " " + window.address,
            window.focused ? 12 : 8))
    })
    ;(source.processes || []).forEach(function(process) {
        result.push(entry("process", process.name || "Process", "PID " + process.pid,
            process.query || "", (process.name || "") + " " + process.pid, 4))
    })
    ;(source.services || []).forEach(function(service) {
        result.push(entry("service", service.id || "Service",
            (service.scope || "") + " · " + (service.description || "Running unit"),
            service.query || "",
            (service.id || "") + " " + (service.description || "") + " "
                + (service.scope || ""), 6))
    })
    ;(source.containers || []).forEach(function(container) {
        result.push(entry("container",
            container.name || container.shortId || "Container",
            (container.runtime || "container") + " · "
                + (container.image || container.status || "running"),
            container.query || "",
            (container.name || "") + " " + (container.id || "") + " "
                + (container.image || "") + " " + (container.composeProject || ""), 6))
    })
    ;(source.devices || []).forEach(function(device) {
        var owner = device.application || device.name || device.kind + " client"
        result.push(entry("device", owner,
            (device.kind || "device") + " · PID " + device.pid,
            device.query || "",
            owner + " " + (device.kind || "") + " " + (device.name || "")
                + " " + device.pid, 5))
    })
    ;(source.gpu || []).forEach(function(client) {
        result.push(entry("gpu", client.application || "GPU client",
            "PID " + client.pid + " · " + Format.basename(client.device),
            client.query || "", (client.application || "") + " gpu " + client.pid, 5))
    })
    ;(source.ports || []).forEach(function(port) {
        result.push(entry("port", "Port " + port.localPort,
            (port.protocol || "") + " · " + (port.state || "listening"),
            port.query || "", String(port.localPort), 3))
    })
    return result
}

function targetCount(values) {
    return (values || []).filter(function(value) {
        return value.kind !== "quick"
    }).length
}

function shortcutCount(values) {
    return (values || []).filter(function(value) {
        return value.kind === "quick"
    }).length
}

function publicEntry(value) {
    return {
        "kind": value.kind,
        "title": value.title,
        "subtitle": value.subtitle,
        "query": value.query
    }
}

function matches(query, values, limit, filter) {
    var needle = String(query || "").trim().toLowerCase()
    if (!needle) return []
    var result = []
    ;(values || []).forEach(function(value) {
        if (filter && !filterMatches(value, filter)) return
        var matchScore = score(value.searchable, needle)
        if (matchScore <= 0) return
        var item = publicEntry(value)
        item.rank = matchScore + value.boost
        result.push(item)
    })
    result.sort(function(left, right) {
        return right.rank - left.rank
            || left.title.localeCompare(right.title)
            || left.subtitle.localeCompare(right.subtitle)
    })
    return result.slice(0, Math.max(1, Number(limit || 7)))
}

function filterMatches(value, filter) {
    if (filter === "all") return true
    var definition = Filters.find(function(candidate) { return candidate.id === filter })
    return !definition || definition.kinds.indexOf(value.kind) >= 0
}

function groupRank(kind) {
    return Groups[kind] ? Groups[kind].rank : 9
}

function groupLabel(kind) {
    return Groups[kind] ? Groups[kind].label : "TARGETS"
}

function browse(values, filter) {
    filter = String(filter || "all")
    var result = (values || []).filter(function(value) {
        return filterMatches(value, filter)
    }).map(publicEntry)
    result.sort(function(left, right) {
        return groupRank(left.kind) - groupRank(right.kind)
            || left.title.localeCompare(right.title)
            || left.subtitle.localeCompare(right.subtitle)
    })
    return result
}

function ownerMatches(target) {
    target = target || {}
    return (target.alternatives || []).map(function(owner) {
        return {
            "kind": "process",
            "title": owner.label || "Process",
            "subtitle": "PID " + owner.pid,
            "query": "pid:" + owner.pid,
            "selected": Number(owner.pid) === Number(target.ownerPid)
        }
    })
}
