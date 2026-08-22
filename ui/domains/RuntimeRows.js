.pragma library
.import "../Format.js" as Format

function count(snapshot) {
    var context = snapshot.context || {}
    var security = snapshot.security || {}
    var total = 6 + Object.keys(security.namespaces || {}).length
        + (security.limits || []).length + (security.libraries || []).length
        + (snapshot.logs || []).length
    if (security.apparmor) total += 1
    if (security.oomScore !== undefined && security.oomScore !== null) total += 1
    if ((context.package || {}).name) total += 1
    if ((context.git || {}).root) total += 1
    var service = context.service || {}
    if (service.id)
        total += 2 + (service.fragmentPath ? 1 : 0) + (service.triggeredBy || []).length
    var container = context.container || {}
    if (container.id)
        total += 2 + (container.ports || []).length
            + (container.mounts || []).length + (container.networks || []).length
    return total
}

function rows(snapshot) {
    var security = snapshot.security || {}
    var context = snapshot.context || {}
    var result = [
        { title: "Executable", subtitle: context.executable || "Unavailable", meta: "" },
        { title: "Working directory", subtitle: context.workingDirectory || "Unavailable", meta: "" },
        { title: "Identity", subtitle: "UID " + (security.uid === undefined ? "unknown" : security.uid) + " · GID " + (security.gid === undefined ? "unknown" : security.gid), meta: (security.groups || []).length ? (security.groups || []).length + " GROUPS" : "" },
        { title: "Security", subtitle: "Seccomp " + (security.seccomp || "Unknown") + " · NoNewPrivileges " + (security.noNewPrivileges === true ? "on" : security.noNewPrivileges === false ? "off" : "unknown"), meta: "" },
        { title: "Namespaces", subtitle: Object.keys(security.namespaces || {}).join(", ") || "Unavailable", meta: "" },
        { title: "Capabilities", subtitle: security.capabilitiesKnown === true ? ((security.capabilities || []).join(", ") || "None effective") : "Unknown", meta: "" }
    ]
    if (security.apparmor)
        result.push({ title: "AppArmor / LSM", subtitle: security.apparmor, meta: "SECURITY" })
    if (security.oomScore !== undefined && security.oomScore !== null)
        result.push({ title: "Out-of-memory priority", subtitle: "Score " + security.oomScore + " · adjustment " + (security.oomAdjustment === undefined || security.oomAdjustment === null ? "unknown" : security.oomAdjustment), meta: "KERNEL" })
    var packageInfo = context.package || {}
    if (packageInfo.name)
        result.push({ title: "Package", subtitle: packageInfo.name + (packageInfo.version ? " · " + packageInfo.version : ""), meta: "PACMAN" })
    var git = context.git || {}
    if (git.root)
        result.push({ title: "Git project", subtitle: git.root, meta: git.branch || "DETACHED" })
    addService(result, context.service || {})
    addContainer(result, context.container || {})
    Object.keys(security.namespaces || {}).sort().forEach(function(name) {
        result.push({ title: "Namespace · " + name, subtitle: String(security.namespaces[name]), meta: "" })
    })
    ;(security.limits || []).forEach(function(limit) {
        result.push({ title: "Limit · " + limit.name, subtitle: "Soft " + limit.soft + " · hard " + limit.hard, meta: limit.unit || "" })
    })
    ;(security.libraries || []).forEach(function(path) {
        result.push({ title: Format.basename(path), subtitle: path, meta: "LIBRARY" })
    })
    ;(snapshot.logs || []).forEach(function(log) {
        result.push({ title: log.message || "Journal entry", subtitle: log.unit || log.timestamp || "", meta: log.priority ? "P" + log.priority : "" })
    })
    return result
}

function addService(result, service) {
    if (!service.id) return
    result.unshift({ title: service.id, subtitle: service.description || "systemd unit", meta: String(service.scope || "").toUpperCase() })
    result.push({ title: "Unit state", subtitle: (service.activeState || "unknown") + " · " + (service.subState || "unknown"), meta: String(service.unitFileState || "").toUpperCase() })
    if (service.fragmentPath)
        result.push({ title: "Unit file", subtitle: service.fragmentPath, meta: "SYSTEMD" })
    ;(service.triggeredBy || []).forEach(function(trigger) {
        result.push({ title: "Configured trigger", subtitle: trigger, meta: "SYSTEMD RELATION" })
    })
}

function addContainer(result, container) {
    if (!container.id) return
    result.unshift({ title: container.name || container.shortId, subtitle: container.image || "Container", meta: String(container.runtime || "CONTAINER").toUpperCase() })
    result.push({ title: "Container policy", subtitle: "Restart " + (container.restartPolicy || "none") + " · privileged " + (container.privileged ? "yes" : "no"), meta: container.state || "" })
    ;(container.ports || []).forEach(function(port) {
        result.push({ title: "Published port", subtitle: Format.addressPort(port.hostAddress || "*", port.hostPort || "—") + " → " + port.containerPort + "/" + port.protocol, meta: "NETWORK" })
    })
    ;(container.mounts || []).forEach(function(mount) {
        result.push({ title: "Mount · " + (mount.destination || "container"), subtitle: mount.source || mount.type || "mount", meta: mount.readOnly ? "READ ONLY" : "READ WRITE" })
    })
    ;(container.networks || []).forEach(function(network) {
        result.push({ title: "Network · " + network.name, subtitle: network.address || network.gateway || "Attached", meta: "NETWORK" })
    })
}
