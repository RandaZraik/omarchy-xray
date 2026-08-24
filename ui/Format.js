.pragma library

function number(value, digits) {
    var numeric = Number(value || 0)
    return isFinite(numeric) ? numeric.toFixed(digits || 0) : "0"
}

function bytes(value) {
    var numeric = Math.max(0, Number(value || 0))
    var units = ["B", "KiB", "MiB", "GiB", "TiB"]
    var index = 0
    while (numeric >= 1024 && index < units.length - 1) {
        numeric /= 1024
        index++
    }
    return (index === 0 ? Math.round(numeric) : numeric.toFixed(numeric >= 10 ? 1 : 2)) + " " + units[index]
}

function rate(value) {
    if (value === null || value === undefined) return "—"
    return bytes(value) + "/s"
}

function duration(seconds) {
    if (seconds === null || seconds === undefined) return "—"
    var value = Math.max(0, Math.round(Number(seconds)))
    var days = Math.floor(value / 86400)
    var hours = Math.floor((value % 86400) / 3600)
    var minutes = Math.floor((value % 3600) / 60)
    if (days) return days + "d " + hours + "h"
    if (hours) return hours + "h " + minutes + "m"
    return minutes + "m"
}

function percent(value) {
    if (value === null || value === undefined) return "—"
    return number(value, Number(value || 0) < 10 ? 1 : 0) + "%"
}

function endpoint(row) {
    if (!row) return ""
    var local = addressPort(row.localAddress, row.localPort)
    if (Number(row.remotePort || 0) === 0) return local
    return local + "  →  " + addressPort(row.remoteAddress, row.remotePort)
}

function addressPort(address, port) {
    var host = String(address || "")
    if (host.indexOf(":") >= 0 && host[0] !== "[") host = "[" + host + "]"
    return host + ":" + String(port || "")
}

function basename(path) {
    var value = String(path || "").replace(/ \(deleted\)$/, "")
    var parts = value.split("/")
    return parts[parts.length - 1] || value
}

function firstCommand(command) {
    if (!command) return ""
    if (typeof command === "string") return command
    var length = Number(command.length)
    if (!isFinite(length) || length < 1) return ""
    var values = []
    for (var index = 0; index < length; index++)
        values.push(String(command[index]))
    return values.join(" ")
}

function icon(name) {
    var icons = {
        "application": "󰣆", "process": "󰆍", "window": "󰖲", "port": "󰒍", "quick": "󰋋",
        "file": "󰈙", "device": "󰋋", "window-point": "󰆿", "focus": "󰢄",
        "folder": "󰉋", "terminal": "󰆍", "pause": "󰏤", "play": "󰐊",
        "stop": "󰓛", "restart": "󰑐", "coverage": "󰦝", "settings": "󰒓",
        "capsule": "󰆧", "close": "󰅖", "refresh": "󰑐", "search": "󰍉",
        "pick": "󰆿", "copy": "󰆏", "baseline": "󰋊", "microphone": "󰍬",
        "camera": "󰄀", "screen": "󰍹", "audio": "󰓃", "audio-capture": "󰕾", "video": "󰕧", "gpu": "󰢮", "sleep": "󰒲",
        "service": "󰒋", "container": "󰡨", "shell": "󰆍", "session": "󰍹",
        "shield": "󰒃", "namespace": "󰅩", "memory": "󰍛", "package": "󰏗", "log": "󰌱",
        "lock": "󰌾", "socket": "󰆨", "network": "󰛳", "pipe": "󰟥", "event": "󰐕", "warning": "󰀪",
        "supervisor": "󰒋", "xray": "󰮄"
    }
    return icons[name] || "•"
}
