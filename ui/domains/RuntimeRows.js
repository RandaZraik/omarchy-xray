.pragma library
.import "../Format.js" as Format

function count(snapshot) {
    snapshot = snapshot || {}
    var security = snapshot.security || {}
    var context = snapshot.context || {}
    var total = 5
    if (security.apparmor) total += 1
    if (security.oomScore !== undefined && security.oomScore !== null) total += 1
    if ((context.package || {}).name) total += 1
    if ((context.git || {}).root) total += 1
    var service = context.service || {}
    if (service.id)
        total += 2 + (service.fragmentPath ? 1 : 0)
            + (service.triggeredBy || []).length
    var container = context.container || {}
    if (container.id)
        total += 2 + (container.ports || []).length
            + (container.mounts || []).length + (container.networks || []).length
    total += Object.keys(security.namespaces || {}).length
    total += (security.limits || []).length
    total += (security.libraries || []).length
    total += (snapshot.logs || []).length
    return total
}

function rows(snapshot) {
    var security = snapshot.security || {}
    var context = snapshot.context || {}
    var result = [
        { section: "workload", title: "Executable", subtitle: context.executable || "Unavailable", meta: "" },
        { section: "workload", title: "Working directory", subtitle: context.workingDirectory || "Unavailable", meta: "" },
        { section: "isolation", title: "Process identity", subtitle: "UID " + (security.uid === undefined ? "unknown" : security.uid) + " · GID " + (security.gid === undefined ? "unknown" : security.gid), meta: (security.groups || []).length ? (security.groups || []).length + " GROUPS" : "" },
        { section: "isolation", title: "Sandbox policy", subtitle: "Seccomp " + (security.seccomp || "Unknown") + " · NoNewPrivileges " + (security.noNewPrivileges === true ? "on" : security.noNewPrivileges === false ? "off" : "unknown"), meta: "" },
        { section: "isolation", title: "Effective capabilities", subtitle: security.capabilitiesKnown === true ? ((security.capabilities || []).join(", ") || "None") : "Unknown", meta: "" }
    ]
    if (security.apparmor)
        result.push({ section: "isolation", title: "AppArmor / LSM", subtitle: security.apparmor, meta: "SECURITY" })
    if (security.oomScore !== undefined && security.oomScore !== null)
        result.push({ section: "resources", title: "Out-of-memory priority", subtitle: "Score " + security.oomScore + " · adjustment " + (security.oomAdjustment === undefined || security.oomAdjustment === null ? "unknown" : security.oomAdjustment), meta: "KERNEL" })
    var packageInfo = context.package || {}
    if (packageInfo.name)
        result.push({ section: "software", title: "Package", subtitle: packageInfo.name + (packageInfo.version ? " · " + packageInfo.version : ""), meta: "PACMAN" })
    var git = context.git || {}
    if (git.root)
        result.push({ section: "software", title: "Git project", subtitle: git.root, meta: git.branch || "DETACHED" })
    addService(result, context.service || {})
    addContainer(result, context.container || {})
    Object.keys(security.namespaces || {}).sort().forEach(function(name) {
        result.push({ section: "namespaces", title: namespaceLabel(name), subtitle: String(security.namespaces[name]), meta: namespaceTag(name) })
    })
    ;(security.limits || []).forEach(function(limit) {
        result.push({ section: "resources", title: limit.name || "Process limit", subtitle: "Soft " + limit.soft + " · hard " + limit.hard, meta: limit.unit || "LIMIT" })
    })
    ;(security.libraries || []).forEach(function(path) {
        result.push({ section: "software", title: Format.basename(path), subtitle: path, meta: "LIBRARY" })
    })
    ;(snapshot.logs || []).forEach(function(log) {
        result.push({ section: "journal", title: log.message || "Journal entry", subtitle: log.unit || log.timestamp || "", meta: log.priority ? "P" + log.priority : "" })
    })
    return result
}

function namespaceLabel(name) {
    var labels = {
        "cgroup": "Control-group namespace",
        "ipc": "IPC namespace",
        "mnt": "Mount namespace",
        "net": "Network namespace",
        "pid": "Process namespace",
        "pid_for_children": "Child process namespace",
        "time": "Time namespace",
        "time_for_children": "Child time namespace",
        "user": "User namespace",
        "uts": "Hostname namespace"
    }
    return labels[name] || ("Namespace · " + name)
}

function namespaceTag(name) {
    var tags = {
        "pid_for_children": "CHILD PID",
        "time_for_children": "CHILD TIME"
    }
    return tags[name] || String(name).replace(/_/g, " ").toUpperCase()
}

function addService(result, service) {
    if (!service.id) return
    result.unshift({ section: "workload", title: service.id, subtitle: service.description || "systemd unit", meta: String(service.scope || "").toUpperCase() })
    result.push({ section: "workload", title: "Unit state", subtitle: (service.activeState || "unknown") + " · " + (service.subState || "unknown"), meta: String(service.unitFileState || "").toUpperCase() })
    if (service.fragmentPath)
        result.push({ section: "workload", title: "Unit file", subtitle: service.fragmentPath, meta: "SYSTEMD" })
    ;(service.triggeredBy || []).forEach(function(trigger) {
        result.push({ section: "workload", title: "Configured trigger", subtitle: trigger, meta: "SYSTEMD RELATION" })
    })
}

function addContainer(result, container) {
    if (!container.id) return
    result.unshift({ section: "container", title: container.name || container.shortId, subtitle: container.image || "Container", meta: String(container.runtime || "CONTAINER").toUpperCase() })
    result.push({ section: "container", title: "Container policy", subtitle: "Restart " + (container.restartPolicy || "none") + " · privileged " + (container.privileged ? "yes" : "no"), meta: container.state || "" })
    ;(container.ports || []).forEach(function(port) {
        result.push({ section: "container", title: "Published port", subtitle: Format.addressPort(port.hostAddress || "*", port.hostPort || "—") + " → " + port.containerPort + "/" + port.protocol, meta: "NETWORK" })
    })
    ;(container.mounts || []).forEach(function(mount) {
        result.push({ section: "container", title: "Mount · " + (mount.destination || "container"), subtitle: mount.source || mount.type || "mount", meta: mount.readOnly ? "READ ONLY" : "READ WRITE" })
    })
    ;(container.networks || []).forEach(function(network) {
        result.push({ section: "container", title: "Network · " + network.name, subtitle: network.address || network.gateway || "Attached", meta: "NETWORK" })
    })
}
