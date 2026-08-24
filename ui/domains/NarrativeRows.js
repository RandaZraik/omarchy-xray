.pragma library

function causeCount(snapshot) {
    return (((snapshot.context || {}).cause || {}).nodes || []).length
}

function explanationCount(snapshot) {
    return (snapshot.explanations || []).length + (snapshot.timeline || []).length
}

function coverageCount(snapshot) {
    var availability = snapshot.coverage || {}
    return (availability.available || []).length + (availability.limited || []).length
}

function alternativeCount(snapshot) {
    return ((snapshot.target || {}).alternatives || []).length
}

function cause(snapshot) {
    var start = (snapshot.context || {}).cause || {}
    return (start.nodes || []).map(function(node, index) {
        return {
            rowType: "cause",
            section: "path",
            step: index + 1,
            icon: node.kind || "process",
            title: node.title || "Process",
            subtitle: node.proof || node.detail || "No source details available",
            meta: String(node.kind || "PROCESS").toUpperCase(),
            searchText: [node.title, node.proof, node.detail, node.kind].join(" ")
        }
    })
}

function explanations(snapshot) {
    var rows = []
    ;(snapshot.explanations || []).forEach(function(explanation) {
        rows.push({
            rowType: "finding",
            section: findingSection(explanation.domain),
            findingId: explanation.id || explanation.title,
            title: explanation.title || "Finding",
            subtitle: explanation.why || "",
            meta: String(explanation.status || "").toUpperCase(),
            tone: explanation.tone || "neutral",
            domain: explanation.domain || "",
            evidence: explanation.evidence || [],
            nextStep: explanation.nextStep || "",
            searchText: [explanation.title, explanation.why,
                (explanation.evidence || []).join(" "), explanation.nextStep,
                explanation.domain, explanation.status].join(" ")
        })
    })
    ;(snapshot.timeline || []).forEach(function(event) {
        rows.push({
            rowType: "timeline",
            section: "timeline",
            title: event.label || "Activity change",
            subtitle: event.timestamp || "",
            meta: String(event.domain || "CHANGE").toUpperCase(),
            searchText: [event.label, event.timestamp, event.domain].join(" ")
        })
    })
    return rows
}

function findingSection(domain) {
    var sections = {
        "connections": "network",
        "files": "files",
        "devices": "devices",
        "runtime": "runtime",
        "logs": "logs",
        "coverage": "coverage"
    }
    return sections[String(domain || "")] || "other"
}

function coverage(snapshot) {
    var availability = snapshot.coverage || {}
    var available = (availability.available || []).map(function(value) {
        return { rowType: "coverage", section: "available", title: value, subtitle: "Source returned complete evidence", meta: "AVAILABLE", available: true }
    })
    var limited = (availability.limited || []).map(function(value) {
        return { rowType: "coverage", section: "limited", title: value, subtitle: "Source was unavailable or incomplete", meta: "LIMITED", available: false }
    })
    return available.concat(limited)
}

function alternatives(snapshot) {
    return ((snapshot.target || {}).alternatives || []).map(function(row) {
        return {
            rowType: "alternative",
            section: Number(row.pid) === Number((snapshot.target || {}).ownerPid)
                ? "selected" : "matches",
            title: row.label || "Process",
            subtitle: "PID " + row.pid,
            meta: Number(row.pid) === Number((snapshot.target || {}).ownerPid) ? "SELECTED" : "MATCH",
            pid: row.pid,
            selected: Number(row.pid) === Number((snapshot.target || {}).ownerPid)
        }
    })
}
