.pragma library
.import "domains/ResourceRows.js" as ResourceRows
.import "domains/RuntimeRows.js" as RuntimeRows
.import "domains/NarrativeRows.js" as NarrativeRows
.import "Format.js" as Format

var Processes = "processes"
var Connections = "connections"
var Files = "files"
var Devices = "devices"
var Runtime = "runtime"
var Cause = "cause"
var Explanations = "explanations"
var Coverage = "coverage"
var Alternatives = "alternatives"

var descriptors = {
    "processes": {
        "title": "Process tree", "selectable": true, "tone": "process",
        "patchKeys": ["processes"]
    },
    "connections": {
        "title": "Connections", "tone": "network", "rowType": "connection",
        "patchKeys": ["connections"], "fallbackSection": "active",
        "sections": [
            {"id": "exposed", "label": "NETWORK-REACHABLE LISTENERS", "icon": "warning", "tone": "danger"},
            {"id": "listeners", "label": "LOCAL LISTENERS", "icon": "socket"},
            {"id": "active", "label": "ACTIVE CONNECTIONS", "icon": "network"},
            {"id": "closing", "label": "CLOSING CONNECTIONS", "icon": "close"}
        ]
    },
    "files": {
        "title": "Files & IPC", "tone": "storage", "patchKeys": ["files", "locks"],
        "fallbackSection": "other", "sections": [
            {"id": "attention", "label": "NEEDS ATTENTION", "icon": "warning", "tone": "danger"},
            {"id": "files", "label": "FILES & DIRECTORIES", "icon": "file"},
            {"id": "devices", "label": "TERMINALS & DEVICES", "icon": "device"},
            {"id": "memory", "label": "SHARED MEMORY", "icon": "memory"},
            {"id": "sockets", "label": "SOCKET HANDLES", "icon": "socket"},
            {"id": "pipes", "label": "PIPES & IPC", "icon": "pipe"},
            {"id": "events", "label": "KERNEL EVENT HANDLES", "icon": "event"},
            {"id": "other", "label": "OTHER DESCRIPTORS", "icon": "file"}
        ]
    },
    "devices": {
        "title": "App device access", "tone": "device", "rowType": "device",
        "patchKeys": ["devices"], "fallbackSection": "media", "sections": [
            {"id": "media", "label": "MEDIA STREAMS", "icon": "audio"},
            {"id": "gpu", "label": "GPU CLIENTS", "icon": "gpu"},
            {"id": "power", "label": "POWER", "icon": "sleep"},
            {"id": "availability", "label": "AVAILABILITY", "icon": "coverage", "tone": "storage"}
        ]
    },
    "runtime": {
        "title": "Runtime & security", "tone": "runtime", "rowType": "runtime",
        "patchKeys": ["context", "security", "logs"], "fallbackSection": "workload",
        "sections": [
            {"id": "workload", "label": "WORKLOAD IDENTITY", "icon": "service"},
            {"id": "isolation", "label": "ISOLATION & PRIVILEGE", "icon": "shield"},
            {"id": "namespaces", "label": "KERNEL NAMESPACES", "icon": "namespace"},
            {"id": "resources", "label": "RESOURCE POLICY", "icon": "memory"},
            {"id": "software", "label": "SOFTWARE ORIGIN", "icon": "package"},
            {"id": "container", "label": "CONTAINER BOUNDARY", "icon": "container"},
            {"id": "journal", "label": "RECENT JOURNAL", "icon": "log"}
        ]
    },
    "cause": {
        "title": "Launch chain", "tone": "process", "rowType": "cause",
        "patchKeys": ["context"], "fallbackSection": "path",
        "sections": [{"id": "path", "label": "CONFIRMED LAUNCH PATH", "icon": "process"}]
    },
    "explanations": {
        "title": "Findings", "tone": "danger", "rowType": "finding",
        "patchKeys": ["explanations", "timeline"], "fallbackSection": "other",
        "sections": [
            {"id": "network", "label": "NETWORK EXPOSURE", "icon": "network", "tone": "network"},
            {"id": "files", "label": "FILES & LOCKS", "icon": "lock", "tone": "storage"},
            {"id": "devices", "label": "PRIVACY & DEVICES", "icon": "device", "tone": "device"},
            {"id": "runtime", "label": "RUNTIME & PRIVILEGE", "icon": "shield", "tone": "runtime"},
            {"id": "logs", "label": "SYSTEM LOGS", "icon": "log", "tone": "danger"},
            {"id": "coverage", "label": "DATA COVERAGE", "icon": "coverage", "tone": "storage"},
            {"id": "other", "label": "OTHER FINDINGS", "icon": "warning", "tone": "danger"},
            {"id": "timeline", "label": "RECENT CHANGES", "icon": "log", "tone": "process"}
        ]
    },
    "coverage": {
        "title": "Data availability", "tone": "storage", "rowType": "coverage",
        "patchKeys": ["coverage"], "fallbackSection": "limited", "sections": [
            {"id": "limited", "label": "LIMITED SOURCES", "icon": "warning", "tone": "danger"},
            {"id": "available", "label": "AVAILABLE SOURCES", "icon": "coverage"}
        ]
    },
    "alternatives": {
        "title": "Matching processes", "selectable": true, "tone": "process",
        "rowType": "alternative", "patchKeys": ["target"],
        "fallbackSection": "matches", "sections": [
            {"id": "selected", "label": "SELECTED OWNER", "icon": "focus"},
            {"id": "matches", "label": "OTHER MATCHES", "icon": "process"}
        ]
    }
}

function title(domain) {
    return descriptors[domain] ? descriptors[domain].title : "Details"
}

function selectable(domain) {
    return descriptors[domain] ? descriptors[domain].selectable === true : false
}

function tone(domain) {
    return descriptors[domain] ? descriptors[domain].tone || "process" : "process"
}

function sectionTone(domain, section) {
    var descriptor = descriptors[domain] || {}
    var sections = descriptor.sections || []
    for (var index = 0; index < sections.length; index++) {
        if (sections[index].id === section)
            return sections[index].tone || descriptor.tone || "process"
    }
    return descriptor.tone || "process"
}

function rowTone(domain, row) {
    if (domain === Explanations && row && row.tone === "attention") return "danger"
    return sectionTone(domain, String((row || {}).sectionId || (row || {}).section || ""))
}

function count(domain, snapshot) {
    if (!snapshot) return 0
    if (domain === Processes) return ResourceRows.processCount(snapshot)
    if (domain === Connections) return ResourceRows.connectionCount(snapshot)
    if (domain === Files) return ResourceRows.fileCount(snapshot)
    if (domain === Devices) return ResourceRows.deviceCount(snapshot)
    if (domain === Runtime) return RuntimeRows.count(snapshot)
    if (domain === Cause) return NarrativeRows.causeCount(snapshot)
    if (domain === Explanations) return NarrativeRows.explanationCount(snapshot)
    if (domain === Coverage) return NarrativeRows.coverageCount(snapshot)
    if (domain === Alternatives) return NarrativeRows.alternativeCount(snapshot)
    return 0
}

function patchTouches(domain, patch) {
    var descriptor = descriptors[String(domain || "")]
    var keys = descriptor ? descriptor.patchKeys || [] : []
    for (var index = 0; index < keys.length; index++) {
        if (Object.prototype.hasOwnProperty.call(patch || {}, keys[index])) return true
    }
    return false
}

function rows(domain, snapshot) {
    if (!snapshot) return []
    if (domain === Processes) return ResourceRows.processes(snapshot)
    if (domain === Connections) return ResourceRows.connections(snapshot)
    if (domain === Files) return ResourceRows.files(snapshot)
    if (domain === Devices) return ResourceRows.devices(snapshot)
    if (domain === Runtime) return RuntimeRows.rows(snapshot)
    if (domain === Cause) return NarrativeRows.cause(snapshot)
    if (domain === Explanations) return NarrativeRows.explanations(snapshot)
    if (domain === Coverage) return NarrativeRows.coverage(snapshot)
    if (domain === Alternatives) return NarrativeRows.alternatives(snapshot)
    return []
}

function filterRows(values, query) {
    var needle = String(query || "").trim().toLowerCase()
    if (!needle) return values || []
    return (values || []).filter(function(row) {
        var haystack = [row.title, row.subtitle, row.meta, row.detail,
            row.remote, row.searchText].join(" ").toLowerCase()
        return haystack.indexOf(needle) >= 0
    })
}

function preparePresentation(domain, values) {
    var descriptor = descriptors[domain] || {}
    var sections = (descriptor.sections || []).slice()
    var source = domain === Files ? ResourceRows.aggregateFiles(values) : (values || [])
    if (!sections.length)
        return {"sectioned": false, "rows": source, "sections": [], "flatRows": source}
    var groups = ({})
    sections.forEach(function(section) { groups[section.id] = [] })
    var fallback = descriptor.fallbackSection || "other"
    if (!groups[fallback]) {
        sections.push({"id": fallback, "label": "OTHER EVIDENCE", "icon": "warning"})
        groups[fallback] = []
    }
    source.forEach(function(row) {
        var section = String(row.section || fallback)
        groups[groups[section] ? section : fallback].push(row)
    })
    var preparedSections = []
    var flatRows = []
    sections.forEach(function(section) {
        var sectionRows = groups[section.id] || []
        if (!sectionRows.length) return
        var sourceCount = 0
        sectionRows.forEach(function(row) {
            sourceCount += Number(row.sourceCount || 1)
        })
        var entryCount = sectionRows.length
        var countLabel = domain === Files && entryCount !== sourceCount
            ? entryCount + " resources  ·  " + sourceCount + " descriptors"
            : String(sourceCount)
        var header = {
            "rowType": "section",
            "id": section.id,
            "sectionId": section.id,
            "section": section.id,
            "title": section.label,
            "label": section.label,
            "icon": section.icon,
            "count": sourceCount,
            "entryCount": entryCount,
            "sourceCount": sourceCount,
            "countLabel": countLabel,
            "collapsed": false
        }
        flatRows.push(header)
        var childStart = flatRows.length
        sectionRows.forEach(function(row) { flatRows.push(row) })
        preparedSections.push({
            "id": section.id,
            "label": section.label,
            "icon": section.icon,
            "count": sourceCount,
            "entryCount": entryCount,
            "sourceCount": sourceCount,
            "countLabel": countLabel,
            "headerIndex": childStart - 1,
            "childStart": childStart,
            "childCount": entryCount,
            "rows": sectionRows
        })
    })
    return {
        "sectioned": true,
        "rows": source,
        "sections": preparedSections,
        "flatRows": flatRows
    }
}

function presentationRowsFromPrepared(domain, prepared, collapsedSections, filtering) {
    prepared = prepared || {"sectioned": false, "rows": [], "sections": []}
    if (!prepared.sectioned) return prepared.rows || []
    var result = []
    ;(prepared.sections || []).forEach(function(section) {
        var key = domain + ":" + section.id
        var collapsed = !filtering && (collapsedSections || {})[key] === true
        result.push({
            "rowType": "section",
            "sectionId": section.id,
            "section": section.id,
            "title": section.label,
            "icon": section.icon,
            "count": section.count,
            "collapsed": collapsed
        })
        if (collapsed) return
        section.rows.forEach(function(row) { result.push(row) })
    })
    return result
}

function presentationRows(domain, values, collapsedSections, filtering) {
    return presentationRowsFromPrepared(
        domain, preparePresentation(domain, values), collapsedSections, filtering
    )
}

function uniqueCount(values) {
    var seen = ({})
    ;(values || []).forEach(function(value) {
        if (value !== undefined && value !== null && String(value) !== "")
            seen[String(value)] = true
    })
    return Object.keys(seen).length
}

function summary(domain, snapshot, allRows) {
    snapshot = snapshot || {}
    if (domain === Runtime) {
        var security = snapshot.security || {}
        return [
            {"label": "SECCOMP", "value": String(security.seccomp || "unknown").toUpperCase()},
            {"label": "NO NEW PRIVS", "value": security.noNewPrivileges === true ? "ON" : security.noNewPrivileges === false ? "OFF" : "UNKNOWN"},
            {"label": "NAMESPACES", "value": String(Object.keys(security.namespaces || {}).length)},
            {"label": "EFFECTIVE CAPS", "value": security.capabilitiesKnown === true ? String((security.capabilities || []).length) : "UNKNOWN"}
        ]
    }
    if (domain === Connections) {
        var connections = snapshot.connections || []
        return [
            {"label": "LISTENERS", "value": String(connections.filter(function(row) { return row.listening === true }).length)},
            {"label": "REMOTE", "value": String(connections.filter(function(row) { return Number(row.remotePort || 0) > 0 }).length)},
            {"label": "NAMESPACES", "value": String(uniqueCount(connections.map(function(row) { return row.networkNamespace })))},
            {"label": "EXPOSED", "value": String(connections.filter(function(row) { return row.externallyReachable === true }).length), "tone": "danger"}
        ]
    }
    if (domain === Files) {
        var files = snapshot.files || []
        var resources = ResourceRows.aggregateFiles(allRows || rows(Files, snapshot))
        return [
            {"label": "DESCRIPTORS", "value": String(files.length)},
            {"label": "RESOURCES", "value": String(resources.filter(function(row) { return row.rowType === "fileGroup" }).length)},
            {"label": "LOCKS", "value": String((snapshot.locks || []).length)},
            {"label": "DELETED", "value": String(files.filter(function(row) { return row.deleted === true }).length), "tone": "danger"}
        ]
    }
    if (domain === Explanations) {
        var findings = snapshot.explanations || []
        return [
            {"label": "FINDINGS", "value": String(findings.length), "tone": "neutral"},
            {"label": "ATTENTION", "value": String(findings.filter(function(row) { return row.tone === "attention" }).length), "tone": "danger"},
            {"label": "EVIDENCE", "value": String(findings.reduce(function(total, row) { return total + (row.evidence || []).length }, 0)), "tone": "neutral"},
            {"label": "CHANGES", "value": String((snapshot.timeline || []).length), "tone": "neutral"}
        ]
    }
    if (domain === Coverage) {
        var coverage = snapshot.coverage || {}
        return [
            {"label": "AVAILABLE", "value": String((coverage.available || []).length)},
            {"label": "LIMITED", "value": String((coverage.limited || []).length), "tone": "warning"}
        ]
    }
    return []
}

function detail(domain, snapshot, allRows, filteredRows, filtering, processSummary) {
    snapshot = snapshot || {}
    allRows = allRows || []
    filteredRows = filteredRows || []
    if (domain === Processes) {
        var process = processSummary || {"processes": 0, "threads": 0, "memoryBytes": 0}
        return process.processes + " processes  ·  " + process.threads + " threads  ·  "
            + Format.bytes(process.memoryBytes) + " resident"
    }
    if (domain === Devices) {
        var active = allRows.filter(function(row) { return row.active === true }).length
        return active + " active  ·  " + filteredRows.length
            + (filtering ? " of " + allRows.length : "") + " records"
    }
    if (domain === Explanations)
        return (snapshot.explanations || []).length + " findings  ·  "
            + (snapshot.timeline || []).length + " changes"
    var labels = {}
    labels[Connections] = "endpoints"
    labels[Files] = "descriptor records"
    labels[Cause] = "launch steps"
    labels[Coverage] = "evidence sources"
    labels[Alternatives] = "process matches"
    var label = labels[domain] || "evidence records"
    return filteredRows.length + (filtering ? " of " + allRows.length : "") + " " + label
}
