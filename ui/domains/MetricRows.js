.pragma library
.import "../Format.js" as Format

function rows(snapshot, theme) {
    snapshot = snapshot || {}
    var metrics = snapshot.metrics || {}
    var devices = snapshot.devices || {}
    return [
        {
            "label": "CPU",
            "value": Format.percent(metrics.cpuPercent),
            "detail": metrics.cpuStatus === "baseline" ? "baseline" : "process share",
            "accent": theme ? theme.cpuAccent : undefined
        },
        {
            "label": "MEM",
            "value": Format.bytes(metrics.memoryBytes),
            "detail": String(metrics.threads || 0) + " threads",
            "accent": theme ? theme.memoryAccent : undefined
        },
        {
            "label": "DISK I/O",
            "value": metrics.ioAvailable === false ? "—" : Format.rate(
                Number(metrics.readBytesPerSecond || 0)
                    + Number(metrics.writeBytesPerSecond || 0)
            ),
            "detail": "read + write",
            "accent": theme ? theme.storageAccent : undefined
        },
        {
            "label": "GPU",
            "value": Format.percent(metrics.gpuPercent),
            "detail": (devices.gpu || []).length + " clients",
            "accent": theme ? theme.deviceAccent : undefined
        },
        {
            "label": "UPTIME",
            "value": Format.duration(metrics.uptimeSeconds),
            "detail": snapshot.samplingPaused ? "paused" : "live",
            "accent": theme ? theme.runtimeAccent : undefined
        }
    ]
}
