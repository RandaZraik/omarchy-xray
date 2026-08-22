.pragma library

function causeCount(snapshot) {
    return (((snapshot.context || {}).cause || {}).nodes || []).length
}

function explanationCount(snapshot) {
    var total = (snapshot.timeline || []).length
    ;(snapshot.explanations || []).forEach(function(row) {
        total += 1 + (row.evidence || []).length + (row.nextStep ? 1 : 0)
    })
    return total
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
            title: (index + 1) + ". " + (node.title || "Process"),
            subtitle: node.proof || node.detail || "No source details available",
            meta: String(node.kind || "PROCESS").toUpperCase()
        }
    })
}

function explanations(snapshot) {
    var rows = []
    ;(snapshot.explanations || []).forEach(function(explanation) {
        rows.push({ title: explanation.title || "Finding", subtitle: explanation.why || "", meta: String(explanation.status || "").toUpperCase() })
        ;(explanation.evidence || []).forEach(function(source) {
            rows.push({ title: "Source", subtitle: String(source), meta: "DETAIL" })
        })
        if (explanation.nextStep)
            rows.push({ title: "Next check", subtitle: explanation.nextStep, meta: "ACTION" })
    })
    ;(snapshot.timeline || []).forEach(function(event) {
        rows.push({ title: event.label || "Activity change", subtitle: event.timestamp || "", meta: String(event.domain || "CHANGE").toUpperCase() })
    })
    return rows
}

function coverage(snapshot) {
    var availability = snapshot.coverage || {}
    var available = (availability.available || []).map(function(value) {
        return { title: value, subtitle: "Available for this target", meta: "AVAILABLE" }
    })
    var limited = (availability.limited || []).map(function(value) {
        return { title: value, subtitle: "X-Ray could not read this information", meta: "UNAVAILABLE" }
    })
    return available.concat(limited)
}

function alternatives(snapshot) {
    return ((snapshot.target || {}).alternatives || []).map(function(row) {
        return {
            title: row.label || "Process",
            subtitle: "PID " + row.pid,
            meta: Number(row.pid) === Number((snapshot.target || {}).ownerPid) ? "SELECTED" : "MATCH",
            pid: row.pid
        }
    })
}
