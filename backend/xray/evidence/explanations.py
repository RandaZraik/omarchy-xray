from __future__ import annotations

from itertools import islice
from typing import Callable


def _first_matches(
    values: object,
    predicate: Callable[[dict[str, object]], bool],
    limit: int,
) -> list[dict[str, object]]:
    if not isinstance(values, list):
        return []
    return list(
        islice(
            (row for row in values if isinstance(row, dict) and predicate(row)),
            limit,
        )
    )


def _explanation(
    *,
    identifier: str,
    tone: str,
    title: str,
    why: str,
    evidence: list[str],
    next_step: str,
    domain: str,
) -> dict[str, object]:
    return {
        "id": identifier,
        "tone": tone,
        "status": "Found",
        "title": title,
        "why": why,
        "evidence": evidence,
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

    public = _first_matches(
        connections, lambda row: bool(row.get("externallyReachable")), 5
    )
    if public:
        endpoints = [
            f"{row.get('localAddress')}:{row.get('localPort')} ({row.get('protocol')})"
            for row in public
        ]
        rows.append(
            _explanation(
                identifier="public-listener",
                tone="attention",
                title="Listening beyond localhost",
                why="These listeners are reachable beyond localhost when the host network and firewall permit it.",
                evidence=endpoints,
                next_step="Open Connections to see which process uses each socket and confirm that public access is intended.",
                domain="connections",
            )
        )

    deleted = _first_matches(files, lambda row: bool(row.get("deleted")), 5)
    if deleted:
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
                next_step="Inspect Files & IPC to identify the process that must release each descriptor.",
                domain="files",
            )
        )

    active_private = _first_matches(
        pipewire,
        lambda row: (
            bool(row.get("active"))
            and row.get("kind")
            in {"microphone", "camera", "screen", "audio-capture", "video"}
        ),
        3,
    )
    for row in active_private:
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

    if isinstance(locks, list) and locks:
        rows.append(
            _explanation(
                identifier="file-locks",
                tone="info",
                title="Kernel file locks are held",
                why="Other processes may be prevented from changing the locked byte ranges while these locks remain.",
                evidence=[
                    f"{row.get('owner') or 'PID ' + str(row.get('pid'))} · {row.get('type')} {row.get('mode')} · inode {row.get('inode')}"
                    for row in locks[:5]
                    if isinstance(row, dict)
                ],
                next_step="Open Files & IPC to review each lock.",
                domain="files",
            )
        )

    capabilities = (
        security.get("capabilities", []) if isinstance(security, dict) else []
    )
    if isinstance(capabilities, list) and capabilities:
        rows.append(
            _explanation(
                identifier="effective-capabilities",
                tone="info",
                title="Linux capabilities are effective",
                why="The process can perform the listed privileged operations without being UID 0.",
                evidence=[str(value) for value in capabilities[:8]],
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

    severe_logs = _first_matches(
        logs,
        lambda row: (
            str(row.get("priority", "9")).isdigit() and int(row.get("priority", 9)) <= 3
        ),
        3,
    )
    if severe_logs:
        rows.append(
            _explanation(
                identifier="journal-errors",
                tone="attention",
                title="Recent error-level journal entries exist",
                why="The journal directly recorded error or higher-priority messages for this process or unit.",
                evidence=[str(row.get("message", ""))[:240] for row in severe_logs],
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
                next_step="Open Data availability to see exactly what X-Ray could not read.",
                domain="coverage",
            )
        )

    if not rows:
        rows.append(
            {
                "id": "no-supported-finding",
                "tone": "quiet",
                "status": "No alerts",
                "title": "Nothing unusual found",
                "why": "X-Ray found no active capture, public listener, deleted-open file, lock, elevated capability, privileged container, or recent system error.",
                "evidence": [],
                "nextStep": "Keep X-Ray open to watch for changes, or inspect a specific area for more detail. This does not guarantee that the app has no bugs.",
                "domain": "timeline",
            }
        )
    return rows
