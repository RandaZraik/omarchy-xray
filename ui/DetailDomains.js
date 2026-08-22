.pragma library
.import "domains/ResourceRows.js" as ResourceRows
.import "domains/RuntimeRows.js" as RuntimeRows
.import "domains/NarrativeRows.js" as NarrativeRows

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
    "processes": { "title": "Process tree", "selectable": true, "patchKeys": ["processes"] },
    "connections": { "title": "Connections", "patchKeys": ["connections"] },
    "files": { "title": "Files & IPC", "patchKeys": ["files", "locks"] },
    "devices": { "title": "App device access", "patchKeys": ["devices"] },
    "runtime": { "title": "Runtime & security", "patchKeys": ["context", "security", "logs"] },
    "cause": { "title": "Launch chain", "patchKeys": ["context"] },
    "explanations": { "title": "Findings", "patchKeys": ["explanations", "timeline"] },
    "coverage": { "title": "Data availability", "patchKeys": ["coverage"] },
    "alternatives": { "title": "Matching processes", "selectable": true, "patchKeys": ["target"] }
}

function title(domain) {
    return descriptors[domain] ? descriptors[domain].title : "Details"
}

function selectable(domain) {
    return descriptors[domain] ? descriptors[domain].selectable === true : false
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
