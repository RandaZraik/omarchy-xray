from __future__ import annotations

from collections.abc import Iterator
from typing import Callable


def _rows(values: object) -> Iterator[dict[str, object]]:
    if isinstance(values, list):
        yield from (row for row in values if isinstance(row, dict))


def _match_preview(
    values: object,
    predicate: Callable[[dict[str, object]], bool],
    limit: int,
) -> tuple[int, list[dict[str, object]]]:
    count = 0
    preview: list[dict[str, object]] = []
    for row in _rows(values):
        if not predicate(row):
            continue
        count += 1
        if len(preview) < limit:
            preview.append(row)
    return count, preview


def _explanation(
    *,
    identifier: str,
    tone: str,
    title: str,
    why: str,
    evidence: list[str],
    next_step: str,
    domain: str,
    evidence_count: int | None = None,
    status: str = "Found",
) -> dict[str, object]:
    return {
        "id": identifier,
        "tone": tone,
        "status": status,
        "title": title,
        "why": why,
        "evidence": evidence,
        "evidenceCount": evidence_count
        if evidence_count is not None
        else len(evidence),
        "nextStep": next_step,
        "domain": domain,
    }


def derive_explanations(snapshot: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    connections = snapshot.get("connections", [])
    files = snapshot.get("files", [])
    locks = snapshot.get("locks", [])
    devices = snapshot.get("devices", {})
    pipewire = devices.get("pipewire", []) if isinstance(devices, dict) else []
    security = snapshot.get("security", {})
    context = snapshot.get("context", {})
    logs = snapshot.get("logs", [])
    coverage = snapshot.get("coverage", {})
    target = snapshot.get("target", {})
    owner_pid = (
        target.get("ownerPid", "unknown") if isinstance(target, dict) else "unknown"
    )

    network_count = 0
    network_listeners: list[dict[str, object]] = []
    multicast_count = 0
    multicast_listeners: list[dict[str, object]] = []
    multicast_is_mdns = True
    for row in _rows(connections):
        if row.get("multicastListener"):
            multicast_count += 1
            multicast_is_mdns = multicast_is_mdns and (
                str(row.get("localAddress")) in {"224.0.0.251", "ff02::fb"}
                and int(row.get("localPort", 0)) == 5353
            )
            if len(multicast_listeners) < 5:
                multicast_listeners.append(row)
        elif row.get("externallyReachable"):
            network_count += 1
            if len(network_listeners) < 5:
                network_listeners.append(row)
    if network_count:
        endpoints = [
            f"{row.get('localAddress')}:{row.get('localPort')} ({row.get('protocol')})"
            for row in network_listeners[:5]
        ]
        rows.append(
            _explanation(
                identifier="public-listener",
                tone="attention",
                title="Network listener is reachable",
                why="These sockets are bound beyond loopback and may accept traffic from a connected network when routing and firewall rules permit it.",
                evidence=endpoints,
                evidence_count=network_count,
                next_step="Open Connections to identify each owner and confirm that network access is intended.",
                domain="connections",
            )
        )

    if multicast_count:
        rows.append(
            _explanation(
                identifier="multicast-listener",
                tone="info",
                title=(
                    "mDNS discovery is active"
                    if multicast_is_mdns
                    else "Multicast listeners are active"
                ),
                why=(
                    "These sockets use the mDNS link-local multicast endpoint for service discovery on the local network."
                    if multicast_is_mdns
                    else "These sockets receive multicast traffic within the scope of their multicast addresses."
                ),
                evidence=[
                    f"{row.get('localAddress')}:{row.get('localPort')} ({row.get('protocol')})"
                    for row in multicast_listeners[:5]
                ],
                evidence_count=multicast_count,
                next_step="Open Connections to identify the owners and confirm that local-network discovery is expected.",
                domain="connections",
            )
        )

    deleted_count, deleted = _match_preview(
        files, lambda row: bool(row.get("deleted")), 5
    )
    if deleted_count:
        rows.append(
            _explanation(
                identifier="deleted-open-files",
                tone="attention",
                title="Deleted files are still held open",
                why="Disk space and old code can remain in use until every owning descriptor closes.",
                evidence=[
                    f"PID {row.get('pid')} · FD {row.get('fd')} · {row.get('target')}"
                    for row in deleted
                ],
                evidence_count=deleted_count,
                next_step="Inspect Files & IPC to identify the process that must release each descriptor.",
                domain="files",
            )
        )

    for row in _rows(pipewire):
        if not (
            row.get("active")
            and row.get("kind")
            in {"microphone", "camera", "screen", "audio-capture", "video"}
        ):
            continue
        kind = str(row.get("kind", "Device")).title()
        rows.append(
            _explanation(
                identifier=f"privacy-{row.get('kind')}-{row.get('pid')}-{row.get('id')}",
                tone="attention",
                title=f"{kind} capture is active",
                why="PipeWire reports a running capture stream owned by the selected process tree.",
                evidence=[
                    f"{row.get('application') or 'Application'} · PID {row.get('pid')}",
                    str(row.get("name") or row.get("mediaClass") or "PipeWire stream"),
                ],
                next_step="Open App device access to see which process is using the stream.",
                domain="devices",
            )
        )

    lock_count, lock_preview = _match_preview(locks, lambda row: True, 5)
    if lock_count:
        rows.append(
            _explanation(
                identifier="file-locks",
                tone="info",
                title="Kernel file locks are held",
                why="Other processes may be prevented from changing the locked byte ranges while these locks remain.",
                evidence=[
                    f"{row.get('owner') or 'PID ' + str(row.get('pid'))} · {row.get('type')} {row.get('mode')} · inode {row.get('inode')}"
                    for row in lock_preview
                ],
                evidence_count=lock_count,
                next_step="Open Files & IPC to review each lock.",
                domain="files",
            )
        )

    capabilities = (
        security.get("capabilities", []) if isinstance(security, dict) else []
    )
    if (
        isinstance(security, dict)
        and security.get("statusAvailable") is True
        and security.get("uid") == 0
    ):
        rows.append(
            _explanation(
                identifier="root-process",
                tone="attention",
                title="The selected process runs as root",
                why="UID 0 gives the selected process unrestricted discretionary access on the host unless another isolation boundary blocks it.",
                evidence=[f"PID {owner_pid} · effective UID 0"],
                next_step="Open Runtime & security and confirm that this workload must run as root.",
                domain="runtime",
            )
        )

    if (
        isinstance(security, dict)
        and security.get("statusAvailable") is True
        and security.get("seccomp") == "Disabled"
    ):
        rows.append(
            _explanation(
                identifier="seccomp-disabled",
                tone="info",
                title="Kernel syscall filtering is disabled",
                why="The selected process reports Seccomp mode 0, so the kernel is not filtering its system calls through seccomp.",
                evidence=[f"PID {owner_pid} · /proc status Seccomp 0"],
                next_step="Open Runtime & security and decide whether this workload should use a seccomp policy.",
                domain="runtime",
            )
        )

    if isinstance(capabilities, list) and capabilities:
        rows.append(
            _explanation(
                identifier="effective-capabilities",
                tone="info",
                title="Linux capabilities are effective",
                why="The process can perform the listed privileged operations without being UID 0.",
                evidence=[str(value) for value in capabilities[:8]],
                evidence_count=len(capabilities),
                next_step="Review Runtime & security and confirm each capability is required.",
                domain="runtime",
            )
        )

    container = context.get("container", {}) if isinstance(context, dict) else {}
    if isinstance(container, dict) and container.get("privileged"):
        rows.append(
            _explanation(
                identifier="privileged-container",
                tone="attention",
                title="The container is privileged",
                why="The runtime reports privileged mode, which substantially reduces host isolation.",
                evidence=[
                    f"{container.get('runtime')} inspect · {container.get('name') or container.get('shortId')}",
                    "HostConfig.Privileged=true",
                ],
                next_step="Review the container context and remove privileged mode if the workload does not require it.",
                domain="runtime",
            )
        )

    severe_log_count, severe_logs = _match_preview(
        logs,
        lambda row: (
            str(row.get("priority", "9")).isdigit() and int(row.get("priority", 9)) <= 3
        ),
        3,
    )
    if severe_log_count:
        rows.append(
            _explanation(
                identifier="journal-errors",
                tone="attention",
                title="Recent error-level journal entries exist",
                why="The journal directly recorded error or higher-priority messages for this process or unit.",
                evidence=[str(row.get("message", ""))[:240] for row in severe_logs],
                evidence_count=severe_log_count,
                next_step="Open Runtime & security and compare message times with recent activity.",
                domain="logs",
            )
        )

    limited = coverage.get("limited", []) if isinstance(coverage, dict) else []
    if isinstance(limited, list) and limited:
        rows.append(
            _explanation(
                identifier="limited-coverage",
                tone="neutral",
                title="Some information is unavailable",
                why="X-Ray could not read every system source, so some related activity may be missing.",
                evidence=[str(value) for value in limited[:5]],
                evidence_count=len(limited),
                next_step="Open Data availability to see exactly what X-Ray could not read.",
                domain="coverage",
            )
        )

    if not rows:
        rows.append(
            _explanation(
                identifier="no-supported-finding",
                tone="quiet",
                status="No alerts",
                title="No supported alerts found",
                why="X-Ray found no active capture, network listener, deleted-open file, lock, root identity, missing seccomp filter, elevated capability, privileged container, or recent system error among the checks it supports.",
                evidence=[],
                next_step="Keep X-Ray open to watch for changes, or inspect a specific area for more detail. This does not guarantee that the app has no bugs.",
                domain="timeline",
            )
        )
    return rows
