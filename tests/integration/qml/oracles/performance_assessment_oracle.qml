import QtQuick
import "../../../../ui/domains/PerformanceAssessment.js" as Assessment

QtObject {
    Component.onCompleted: {
        var failures = []
        function require(value, name) { if (!value) failures.push(name) }
        function check(id, section, scope, status, measurements) {
            return {id: "performance-" + id, section: section, scope: scope, status: status,
                tone: status === "Observed" ? "attention" : "neutral", measurements: measurements || {}}
        }
        var work = check("cpu-work", "cpu", "Selected tree", "Quiet", {cores: 0.36, sampledProcesses: 32, secondsMin: 1.12})
        var wait = check("cpu-wait", "cpu", "Selected threads", "Unavailable")
        var quiet = Assessment.assessment({checks: [work, wait], status: "limited"})
        require(quiet.headline === "No cause identified yet", "quiet claims health")
        require(quiet.resources[0].title === "About 36% of one CPU core", "wrong CPU denominator")
        require(quiet.resources[0].badge === "PARTIAL", "scheduler gap hidden")
        require(quiet.limitations.indexOf("could not be measured") >= 0, "missing scheduler limitation")
        require(quiet.resources[1].title === "Not enough data", "absent memory appears quiet")

        var host = check("pressure-io-Host", "io", "Host", "Observed", {somePercent: 15, seconds: 2, someAvg10: 3})
        var hostResult = Assessment.assessment({checks: [work, host]})
        require(hostResult.headline === "System-wide waiting observed", "host blamed on target")
        require(hostResult.resources[2].badge === "SYSTEM", "host scope lost")
        require(hostResult.resources[2].detail.indexOf("Estimated 15.00% of 2.00s") >= 0, "interval estimate mislabeled")
        require(hostResult.resources[2].detail.indexOf("10s average: 3.00%") >= 0, "pressure windows conflated")

        var throttle = check("throttle-/shared", "cpu", "Cgroup /shared", "Observed", {nr_throttled: 5, seconds: 2})
        var local = Assessment.assessment({checks: [work, throttle, host]})
        require(local.headline === "Clues worth investigating", "local signal missing")
        require(local.resources[0].title === "A CPU limit held work back", "throttling not explained")
        require(local.resources[0].detail.indexOf("other processes may share it") >= 0, "shared scope attributed to target")
        require(Assessment.assessment({}).headline === "No performance data", "legacy claims evidence")
        require(Assessment.assessment({checks: [work], originalCheckCount: 50}).limitations.indexOf("1 of 50 measurements retained") >= 0, "truncation hidden")
        var killed = check("memory-events-/shared", "memory", "Cgroup /shared", "Observed", {high: 0, max: 0, oom: 0, oom_kill: 1, seconds: 1})
        require(Assessment.assessment({checks: [killed]}).resources[1].title === "Processes were killed for lack of memory", "OOM kill assumed group limit")
        killed.measurements.oom_kill = 0
        killed.measurements.oom = 1
        require(Assessment.assessment({checks: [killed]}).resources[1].title === "Memory allocation ran into a limit", "OOM event assumed failed allocation")
        work.measurements = undefined
        var missing = Assessment.assessment({checks: [work, {section: "cpu", status: "Observed", tone: "attention"}]})
        require(JSON.stringify(missing).indexOf("NaN") < 0, "missing measurements rendered as NaN")
        require(Assessment.assessment({checks: [work]}).resources[0].title === "CPU use was not recorded", "missing CPU value displayed as zero")
        work.measurements = {}
        require(Assessment.assessment({checks: [work]}).resources[0].badge === "PARTIAL", "empty CPU value claimed measured")
        work.status = "Baseline"
        require(Assessment.assessment({checks: [work]}).resources[0].title === "Waiting for another sample", "baseline shown as zero")
        console.log("XRAY_ASSESSMENT " + JSON.stringify({failures: failures}))
        Qt.quit()
    }
}
