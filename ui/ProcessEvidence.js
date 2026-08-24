.pragma library
.import "Format.js" as Format

function _commandValues(row) {
    var raw = row ? row.command : null
    if (!raw) return []
    if (typeof raw === "string") return raw ? [raw] : []
    var length = Number(raw.length)
    if (!isFinite(length) || length < 1) return []
    var values = []
    for (var index = 0; index < length; index++)
        values.push(String(raw[index]))
    return values
}

function _basenameCommand(value) {
    // argv[0] is normally just the executable path, but launchers can place
    // an entire command line in the first NUL-delimited field. Only basename
    // the leading executable token; applying _basename() to the whole field
    // would incorrectly jump to the final path mentioned in its arguments.
    var text = String(value || "")
    var match = text.match(/^(\s*)(\S+)([\s\S]*)$/)
    return match ? match[1] + Format.basename(match[2]) + match[3] : text
}

function _executableName(value) {
    var text = String(value || "").trim()
    var whitespace = text.search(/\s/)
    return Format.basename(whitespace < 0 ? text : text.slice(0, whitespace))
}

function _isInterpreter(value) {
    return /^(python(?:\d+(?:\.\d+)*)?|pypy\d*|bash|sh|zsh|fish|node|ruby|perl)$/.test(
        String(value || "").toLowerCase()
    )
}

function command(row) {
    var value = Format.firstCommand((row || {}).command)
    if (value) return value
    return String((row || {}).executable || "Command unavailable")
}

function presentation(row) {
    var values = _commandValues(row)
    if (!values.length)
        return { "command": command(row), "launcher": "" }
    var start = 0
    var first = _executableName(values[0])
    if (_isInterpreter(first) && values.length > 1
            && String(values[1]).charAt(0) !== "-")
        start = 1
    var focused = values.slice(start)
    focused[0] = _basenameCommand(focused[0])
    return {
        "command": focused.join(" "),
        "launcher": start === 1 ? "via " + first : ""
    }
}

function conciseCommand(row) {
    return presentation(row).command
}

function commandLauncher(row) {
    return presentation(row).launcher
}

function user(row) {
    if (row && row.user !== undefined && row.user !== null && String(row.user))
        return String(row.user)
    var uid = Number((row || {}).uid)
    return isFinite(uid) && uid >= 0 ? "UID " + uid : "unknown"
}

function state(row) {
    var code = String((row || {}).state || "?").charAt(0)
    var labels = {
        "R": "running",
        "S": "sleeping",
        "D": "disk wait",
        "T": "stopped",
        "t": "tracing",
        "Z": "zombie",
        "X": "dead",
        "I": "idle",
        "P": "parked"
    }
    return labels[code] || "state " + code
}

function filter(rows, query) {
    var needle = String(query || "").trim().toLowerCase()
    if (!needle) return (rows || []).slice()
    return (rows || []).filter(function(row) {
        // Keep this field set aligned with btop's process filter: PID,
        // program name, command, and user. Extra process metadata must not
        // create results that the task manager cannot reproduce.
        var haystack = [
            row.name,
            row.pid,
            row.user === undefined || row.user === null || String(row.user) === ""
                ? row.uid : row.user,
            command(row)
        ].map(function(value) { return String(value === undefined ? "" : value) })
            .join(" ").toLowerCase()
        return haystack.indexOf(needle) >= 0
    })
}

function numeric(row, key) {
    var value
    if (key === "cpu") value = row.cpuPercent
    else if (key === "memory") value = row.memoryBytes
    else if (key === "threads") value = row.threads
    else if (key === "pid") value = row.pid
    else if (key === "read") value = row.readBytesPerSecond
    else if (key === "write") value = row.writeBytesPerSecond
    else if (key === "io") {
        var readKnown = row.readBytesPerSecond !== null
            && row.readBytesPerSecond !== undefined
        var writeKnown = row.writeBytesPerSecond !== null
            && row.writeBytesPerSecond !== undefined
        if (!readKnown && !writeKnown)
            return null
        value = Number(row.readBytesPerSecond || 0) + Number(row.writeBytesPerSecond || 0)
    }
    if (value === null || value === undefined || !isFinite(Number(value))) return null
    return Number(value)
}

function sort(rows, key, descending) {
    var result = (rows || []).slice()
    key = String(key || "tree")
    if (key === "tree") return result
    result.sort(function(left, right) {
        var leftValue
        var rightValue
        if (key === "user" || key === "command" || key === "program") {
            leftValue = key === "user"
                ? user(left).toLowerCase()
                : key === "command"
                    ? command(left).toLowerCase()
                    : String(left.name || "").toLowerCase()
            rightValue = key === "user"
                ? user(right).toLowerCase()
                : key === "command"
                    ? command(right).toLowerCase()
                    : String(right.name || "").toLowerCase()
        } else {
            leftValue = numeric(left, key)
            rightValue = numeric(right, key)
            if (leftValue === null && rightValue === null)
                return Number(left.pid || 0) - Number(right.pid || 0)
            if (leftValue === null) return 1
            if (rightValue === null) return -1
        }
        var order = leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0
        if (order === 0) order = Number(left.pid || 0) - Number(right.pid || 0)
        return descending ? -order : order
    })
    return result
}

function summary(rows) {
    return (rows || []).reduce(function(total, row) {
        total.processes += 1
        total.threads += Math.max(0, Number(row.threads || 0))
        total.memoryBytes += Math.max(0, Number(row.memoryBytes || 0))
        return total
    }, { "processes": 0, "threads": 0, "memoryBytes": 0 })
}
