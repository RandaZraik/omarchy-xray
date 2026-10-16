.pragma library
.import "../Format.js" as Format

function measured(check) {
    return check && (check.status === "Quiet" || check.status === "Observed")
}

function numeric(value) {
    return typeof value === "number" && isFinite(value) && value >= 0
}

function assessment(performance) {
    var checks = (performance || {}).checks || []
    var signals = checks.filter(function(check) {
        return check.status === "Observed" && check.tone === "attention"
    })
    var local = signals.filter(function(check) { return check.scope !== "Host" })
    var baseline = checks.some(function(check) { return check.status === "Baseline" })
    var missing = checks.filter(function(check) {
        return check.status === "Unavailable" || check.status === "Limited"
    })
    var work = checks.find(function(check) { return check.id === "performance-cpu-work" })
    var wait = checks.find(function(check) { return check.id === "performance-cpu-wait" })
    var limitations = []
    var originalCount = (performance || {}).originalCheckCount
    if (numeric(originalCount) && originalCount > checks.length)
        limitations.push(checks.length + " of " + originalCount + " measurements retained. The others were omitted to keep the recording within its size limit.")
    if (!checks.length) limitations.push("This recording has no performance measurements.")
    if (wait && !measured(wait))
        limitations.push(wait.status === "Baseline"
            ? "Time spent waiting for CPU needs another sample."
            : "Time spent waiting for CPU could not be measured on this system.")
    if (missing.some(function(check) { return check !== wait }) || (performance || {}).status === "limited")
        limitations.push("Some checks are incomplete. Conclusions cover only the data available.")
    limitations.push("These checks do not measure slow code, network response time, GPU stalls, or time waiting on app locks.")

    return {
        headline: !checks.length ? "No performance data"
            : local.length ? "Clues worth investigating"
            : signals.length ? "System-wide waiting observed"
            : baseline ? "Gathering measurements…" : "No cause identified yet",
        description: !checks.length ? "Open a live target to collect measurements."
            : local.length ? "These measurements may help explain the slowdown. Shared resources can include other apps."
            : signals.length ? "Tasks on this computer spent time waiting. This may include other apps."
            : "These checks haven’t explained the slowdown in this sample.",
        context: work && work.measurements && measured(work) && numeric(work.measurements.sampledProcesses)
            ? work.measurements.sampledProcesses + (work.measurements.sampledProcesses === 1 ? " process sampled" : " processes sampled")
                + (work.measurements.secondsMin > 0
                    ? " · about " + Format.number(work.measurements.secondsMin, 1) + "s between samples" : "")
            : "Waiting for comparable samples",
        resources: ["cpu", "memory", "io"].map(function(section) {
            return resource(section, checks, signals, work)
        }),
        limitations: limitations.join("\n\n"),
        coverageLabel: numeric(originalCount) && originalCount > checks.length
            ? checks.length + " of " + originalCount + " checks retained · view limits"
            : missing.length ? missing.length + (missing.length === 1 ? " check unavailable or incomplete" : " checks unavailable or incomplete")
            : (performance || {}).status === "limited" ? "Some measurements are incomplete"
            : "What these checks can’t measure"
    }
}

function resource(section, checks, signals, work) {
    var candidates = signals.filter(function(check) { return check.section === section })
    candidates.sort(function(a, b) {
        function priority(check) {
            return (check.scope === "Host" ? 10 : 0)
                + (String(check.id || "").indexOf("performance-pressure-") === 0 ? 1 : 0)
        }
        return priority(a) - priority(b)
    })
    // Prefer a clue connected to the target over unrelated host activity.
    var signal = candidates[0]
    var rows = checks.filter(function(check) { return check.section === section })
    var result = {
        label: {cpu: "CPU", memory: "Memory", io: "Disk & I/O"}[section],
        title: "No signal in this sample",
        detail: "The measured checks stayed below their highlight thresholds.",
        badge: "MEASURED",
        attention: !!signal
    }
    if (!rows.length || !rows.some(measured)) {
        result.title = rows.some(function(check) { return check.status === "Baseline" })
            ? "Waiting for another sample" : "Not enough data";
        result.detail = "No conclusion is available for this resource yet."
        result.badge = "PENDING"
    } else if (rows.some(function(check) { return !measured(check) })) {
        result.badge = "PARTIAL"
        result.detail = "No signal in the available checks. Some measurements are missing."
    }
    if (section === "cpu" && work && measured(work)) {
        if (numeric((work.measurements || {}).cores)) {
            result.title = "About " + Format.number(work.measurements.cores * 100, 0) + "% of one CPU core"
            result.detail = "Across the sampled processes. CPU use alone doesn’t identify a bottleneck."
        } else {
            result.title = "CPU use was not recorded"
            result.detail = "This recording has no usable CPU measurement."
            result.badge = "PARTIAL"
        }
    }
    if (!signal) return result
    var values = signal.measurements || {}
    var id = String(signal.id || "")
    function has(names) { return names.every(function(name) { return numeric(values[name]) }) }
    var shared = signal.scope === "Host"
        ? "Across this computer; other apps may be responsible."
        : "In a resource group containing this app; other processes may share it."
    result.badge = signal.scope === "Host" ? "SYSTEM" : "OBSERVED"
    if (id.indexOf("performance-throttle-") === 0 && has(["nr_throttled", "seconds"])) {
        result.title = "A CPU limit held work back"
        result.detail = values.nr_throttled + " throttled periods over " + Format.number(values.seconds, 2) + "s. " + shared
    } else if (id === "performance-cpu-wait" && has(["delayedThreads"])) {
        result.title = "Threads waited for CPU time"
        result.detail = values.delayedThreads + " threads crossed the wait threshold. This measures waiting to run, not waiting on app locks."
    } else if (id.indexOf("performance-memory-events-") === 0 && has(["seconds", "high", "max", "oom", "oom_kill"])) {
        result.title = values.high > 0 || values.max > 0 ? "Memory limits were hit"
            : values.oom_kill > 0 ? "Processes were killed for lack of memory" : "Memory allocation ran into a limit"
        result.detail = "Over " + Format.number(values.seconds, 2) + "s: " + values.high + " reclaim events, " + values.max + " limit events, " + values.oom + " out-of-memory events, " + values.oom_kill + " kills. " + shared
    } else if (id === "performance-blocked" && has(["blockedThreads"])) {
        result.title = "Threads were waiting in the kernel"
        result.detail = values.blockedThreads + " threads at this instant. This can involve I/O, but does not establish a disk fault."
    } else if (id.indexOf("performance-pressure-") === 0 && has(["somePercent", "seconds"])) {
        result.title = {cpu: "Tasks waited for CPU", memory: "Tasks waited for memory", io: "Tasks waited for I/O"}[section]
        result.detail = "Estimated " + Format.number(values.somePercent, 2) + "% of " + Format.number(values.seconds, 2) + "s with some tasks stalled. "
            + (numeric(values.someAvg10)
                ? "Kernel 10s average: " + Format.number(values.someAvg10, 2) + "%. " : "") + shared
    } else {
        result.title = "A clue was recorded"
        result.detail = "Open all measurements for the recorded evidence. Numeric details are unavailable."
        result.badge = "PARTIAL"
    }
    return result
}
