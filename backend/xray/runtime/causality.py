from __future__ import annotations

from xray.config import LIMITS
from xray.processes.identity import parse_stat
from xray.system.procfs import ProcFs, parse_key_values


_SHELLS = {"bash", "dash", "fish", "nu", "sh", "zsh"}
_TERMINALS = {"alacritty", "foot", "ghostty", "kitty", "wezterm", "xterm"}
_SESSIONS = {"screen", "sshd", "tmux"}
_SUPERVISORS = {
    "containerd-shim",
    "dumb-init",
    "pm2",
    "runit",
    "s6-svscan",
    "supervisord",
    "systemd",
    "tini",
}


def _node_kind(name: str) -> str:
    normalized = name.casefold()
    if normalized in _SHELLS:
        return "shell"
    if normalized in _TERMINALS:
        return "terminal"
    if normalized in _SESSIONS:
        return "session"
    if normalized in _SUPERVISORS:
        return "supervisor"
    return "process"


def _process_node(proc: ProcFs, pid: int) -> tuple[dict[str, object], int] | None:
    stat_result = proc.read(pid, "stat")
    if not stat_result.available:
        return None
    try:
        stat = parse_stat(stat_result.value)
    except (TypeError, ValueError):
        return None
    status = proc.read(pid, "status")
    values = parse_key_values(status.value) if status.available else {}
    name = values.get("Name", str(stat["comm"]))
    return (
        {
            "id": f"process:{pid}:{stat['start_time']}",
            "kind": _node_kind(name),
            "title": name,
            "detail": f"PID {pid}",
            "pid": pid,
            "proof": f"/proc/{pid}/stat reports parent PID {stat['ppid']}",
        },
        int(stat["ppid"]),
    )


def process_ancestry(proc: ProcFs, pid: int) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    seen: set[int] = set()
    current = pid
    while current > 0 and current not in seen and len(nodes) < LIMITS.cause_nodes:
        seen.add(current)
        result = _process_node(proc, current)
        if not result:
            break
        node, parent = result
        nodes.append(node)
        if parent <= 0 or parent == current:
            break
        current = parent
    nodes.reverse()
    return nodes


def _unit_nodes(service: dict[str, object]) -> list[dict[str, object]]:
    if not service:
        return []
    identifier = str(service.get("id", "Systemd unit"))
    return [
        {
            "id": f"unit:{service.get('scope', '')}:{identifier}",
            "kind": "service",
            "title": identifier,
            "detail": str(service.get("description", "")) or identifier,
            "proof": str(service.get("fragmentPath", ""))
            or f"systemd {service.get('scope', '')} unit metadata",
            "pid": int(service.get("mainPid", 0)),
        }
    ]


def _container_node(container: dict[str, object]) -> list[dict[str, object]]:
    if not container:
        return []
    name = str(container.get("name", "")) or str(container.get("shortId", "Container"))
    detail = " · ".join(
        value
        for value in (
            str(container.get("image", "")),
            str(container.get("composeProject", "")),
        )
        if value
    )
    return [
        {
            "id": f"container:{container.get('runtime', '')}:{container.get('id', '')}",
            "kind": "container",
            "title": name,
            "detail": detail or str(container.get("runtime", "Container")),
            "proof": f"{container.get('runtime', 'container')} inspect reports host PID {container.get('pid', 0)}",
            "pid": int(container.get("pid", 0)),
        }
    ]


def build_cause_chain(
    proc: ProcFs,
    owner_pid: int,
    service: dict[str, object],
    container: dict[str, object],
) -> dict[str, object]:
    ancestry = process_ancestry(proc, owner_pid)
    semantic_nodes = _unit_nodes(service) + _container_node(container)
    replacements: dict[int, list[dict[str, object]]] = {}
    for node in semantic_nodes:
        semantic_pid = int(node.get("pid", 0))
        if semantic_pid > 0:
            replacements.setdefault(semantic_pid, []).append(node)
    merged: list[dict[str, object]] = []
    for node in ancestry:
        replacement_nodes = replacements.pop(int(node.get("pid", 0)), [])
        if replacement_nodes:
            merged.extend(
                {**replacement, "processProof": node.get("proof", "")}
                for replacement in replacement_nodes
            )
        else:
            merged.append(node)
    unmatched = [node for node in semantic_nodes if int(node.get("pid", 0)) <= 0]
    unmatched.extend(node for group in replacements.values() for node in group)
    nodes = [*merged[:-1], *unmatched, merged[-1]] if merged else unmatched
    service_id = str(service.get("id", "")) if service else ""
    if container and service and service_id.endswith(".service"):
        summary = f"Running in {container.get('name') or container.get('shortId') or 'a container'}, managed by {service_id}"
        status = "Confirmed"
    elif container and service:
        summary = f"Running in {container.get('name') or container.get('shortId') or 'a container'} inside systemd scope {service_id or 'unknown'}"
        status = "Confirmed"
    elif container:
        summary = f"Running inside {container.get('name') or container.get('shortId') or 'a container'}"
        status = "Confirmed"
    elif service:
        summary = (
            f"Grouped inside systemd scope {service_id}"
            if service_id.endswith(".scope")
            else f"Started by {service_id or 'a systemd service'}"
        )
        status = "Confirmed"
    else:
        session = next(
            (
                node
                for node in ancestry
                if node.get("kind") in {"session", "terminal", "shell"}
            ),
            None,
        )
        if session:
            summary = f"Current parent chain passes through {session['title']}; the original launcher is no longer available"
            status = "Partial"
        elif ancestry:
            summary = "X-Ray found the current process chain, but no managing service or container"
            status = "Partial"
        else:
            summary = "Start information is unavailable for this process"
            status = "Unavailable"
    return {
        "status": status,
        "summary": summary,
        "nodes": nodes[-LIMITS.cause_nodes :],
    }
