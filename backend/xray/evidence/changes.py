from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Final

from xray.config import LIMITS


DOMAIN_LABELS: Final[dict[str, str]] = {
    "processes": "process",
    "connections": "connection",
    "files": "file",
    "pipewire": "device",
    "gpu": "device",
    "inhibitors": "device",
    "runtime": "runtime",
}
PUBLIC_DOMAIN: Final[dict[str, str]] = {
    "pipewire": "devices",
    "gpu": "devices",
    "inhibitors": "devices",
}
METRIC_NAMES: Final[tuple[str, ...]] = (
    "cpuPercent",
    "memoryBytes",
    "gpuPercent",
)
PUBLIC_DOMAINS: Final[tuple[str, ...]] = (
    "processes",
    "connections",
    "files",
    "devices",
    "runtime",
)


def _keys(snapshot: dict[str, object], name: str, key) -> set[str]:
    rows = snapshot.get(name, [])
    return (
        {str(key(row)) for row in rows if isinstance(row, dict)}
        if isinstance(rows, list)
        else set()
    )


def snapshot_sets(
    snapshot: dict[str, object],
    reused: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    """Build domain fingerprints, reusing immutable cached domains when safe."""
    result = dict(reused or {})
    wanted = set(DOMAIN_LABELS) - result.keys()
    if "processes" in wanted:
        result["processes"] = _keys(
            snapshot, "processes", lambda row: row.get("id", "")
        )
    if "connections" in wanted:
        result["connections"] = _keys(
            snapshot,
            "connections",
            lambda row: (
                f"{row.get('networkNamespace')}:{row.get('inode')}:{row.get('protocol')}:"
                f"{row.get('localAddress')}:{row.get('localPort')}:"
                f"{row.get('remoteAddress')}:{row.get('remotePort')}:{row.get('state')}"
            ),
        )
    if "files" in wanted:
        file_keys = _keys(
            snapshot,
            "files",
            lambda row: f"fd:{row.get('pid')}:{row.get('fd')}:{row.get('target')}",
        )
        file_keys.update(
            _keys(
                snapshot,
                "locks",
                lambda row: (
                    f"lock:{row.get('owner')}:{row.get('type')}:{row.get('mode')}:"
                    f"{row.get('inode')}:{row.get('start')}:{row.get('end')}"
                ),
            )
        )
        result["files"] = file_keys

    device_domains = wanted & {"pipewire", "gpu", "inhibitors"}
    if device_domains:
        devices = (
            snapshot.get("devices", {})
            if isinstance(snapshot.get("devices"), dict)
            else {}
        )
        if "pipewire" in device_domains:
            rows = (
                devices.get("pipewire", [])
                if isinstance(devices.get("pipewire"), list)
                else []
            )
            result["pipewire"] = {
                f"pipewire:{row.get('pid')}:{row.get('id')}:{row.get('active')}:{row.get('kind')}:{row.get('source')}:{','.join(str(value) for value in row.get('sourceIds', []))}"
                for row in rows
                if isinstance(row, dict)
            }
        if "gpu" in device_domains:
            rows = (
                devices.get("gpu", []) if isinstance(devices.get("gpu"), list) else []
            )
            result["gpu"] = {
                f"gpu:{row.get('pid')}:{row.get('device')}:{row.get('clientId')}"
                for row in rows
                if isinstance(row, dict)
            }
        if "inhibitors" in device_domains:
            rows = (
                devices.get("inhibitors", [])
                if isinstance(devices.get("inhibitors"), list)
                else []
            )
            result["inhibitors"] = {
                f"inhibitor:{row.get('pid')}:{row.get('what')}:{row.get('mode')}"
                for row in rows
                if isinstance(row, dict)
            }

    if "runtime" in wanted:
        context = (
            snapshot.get("context", {})
            if isinstance(snapshot.get("context"), dict)
            else {}
        )
        service = (
            context.get("service", {})
            if isinstance(context.get("service"), dict)
            else {}
        )
        container = (
            context.get("container", {})
            if isinstance(context.get("container"), dict)
            else {}
        )
        cause = (
            context.get("cause", {}) if isinstance(context.get("cause"), dict) else {}
        )
        cause_nodes = (
            cause.get("nodes", []) if isinstance(cause.get("nodes"), list) else []
        )
        runtime_keys = {
            f"cause:{row.get('id')}"
            for row in cause_nodes
            if isinstance(row, dict) and row.get("id")
        }
        if service.get("id"):
            runtime_keys.add(
                f"service:{service.get('scope')}:{service.get('id')}:{service.get('activeState')}:{service.get('subState')}"
            )
        if container.get("id"):
            runtime_keys.add(
                f"container:{container.get('runtime')}:{container.get('id')}:{container.get('state')}"
            )
        result["runtime"] = runtime_keys
    return result


def compare_snapshots(
    before: dict[str, object], after: dict[str, object]
) -> dict[str, object]:
    return compare_states(
        SnapshotState.from_snapshot(before), SnapshotState.from_snapshot(after)
    )


@dataclass(frozen=True)
class SnapshotState:
    domains: dict[str, set[str]]
    domain_known: dict[str, bool]
    metrics: dict[str, float | None]

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, object],
        reused_domains: dict[str, set[str]] | None = None,
    ) -> SnapshotState:
        source = snapshot.get("metrics", {})
        metrics = source if isinstance(source, dict) else {}
        coverage = snapshot.get("coverage", {})
        coverage = coverage if isinstance(coverage, dict) else {}
        domain_status = coverage.get("domains", {})
        domain_status = domain_status if isinstance(domain_status, dict) else {}

        def metric_value(key: str) -> float | None:
            value = metrics.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            normalized = float(value)
            return normalized if math.isfinite(normalized) else None

        return cls(
            snapshot_sets(snapshot, reused_domains),
            {
                name: str(
                    domain_status.get(
                        name,
                        domain_status.get("devices", "available")
                        if name in PUBLIC_DOMAIN
                        else "available",
                    )
                )
                == "available"
                for name in DOMAIN_LABELS
            },
            {key: metric_value(key) for key in METRIC_NAMES},
        )


def compare_states(before: SnapshotState, after: SnapshotState) -> dict[str, object]:
    domains: dict[str, dict[str, object]] = {
        name: {"added": 0, "removed": 0} for name in PUBLIC_DOMAINS
    }
    public_known: dict[str, list[bool]] = {name: [] for name in domains}
    for name in after.domains:
        known = before.domain_known.get(name, True) and after.domain_known.get(
            name, True
        )
        public = PUBLIC_DOMAIN.get(name, name)
        domains[public]["added"] += (
            len(after.domains[name] - before.domains[name]) if known else 0
        )
        domains[public]["removed"] += (
            len(before.domains[name] - after.domains[name]) if known else 0
        )
        public_known[public].append(known)
    for name, states in public_known.items():
        if states and not all(states):
            domains[name]["status"] = "partial" if any(states) else "unavailable"
    metric_delta: dict[str, float | None] = {}
    for key in METRIC_NAMES:
        before_value = before.metrics.get(key)
        after_value = after.metrics.get(key)
        metric_delta[key] = (
            round(after_value - before_value, 1)
            if before_value is not None and after_value is not None
            else None
        )
    return {"domains": domains, "metrics": metric_delta}


def unchanged() -> dict[str, object]:
    return {
        "domains": {name: {"added": 0, "removed": 0} for name in PUBLIC_DOMAINS},
        "metrics": {name: 0.0 for name in METRIC_NAMES},
    }


class EvidenceHistory:
    def __init__(self, event_limit: int = LIMITS.timeline_events) -> None:
        self.event_limit = event_limit
        self.baseline: SnapshotState | None = None
        self.previous: SnapshotState | None = None
        self.events: list[dict[str, object]] = []

    def reset(self, snapshot: dict[str, object]) -> None:
        state = SnapshotState.from_snapshot(snapshot)
        self.baseline = state
        self.previous = state
        self.events = []

    def track(
        self,
        snapshot: dict[str, object],
        reused_domains: tuple[str, ...] = (),
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        if self.baseline is None or self.previous is None:
            self.reset(snapshot)
            return unchanged(), []
        reusable = {
            name: self.previous.domains[name]
            for name in reused_domains
            if name in self.previous.domains
        }
        current = SnapshotState.from_snapshot(snapshot, reusable)
        previous_domains = dict(self.previous.domains)
        previous_known = dict(self.previous.domain_known)
        current_domains = dict(current.domains)
        current_known = dict(current.domain_known)
        baseline_domains = dict(self.baseline.domains)
        baseline_known = dict(self.baseline.domain_known)
        for name in DOMAIN_LABELS:
            if not current_known[name]:
                current_domains[name] = set(previous_domains[name])
                current_known[name] = previous_known[name]
            elif not previous_known[name]:
                previous_domains[name] = set(current_domains[name])
                previous_known[name] = True
                if not baseline_known[name]:
                    baseline_domains[name] = set(current_domains[name])
                    baseline_known[name] = True
        comparable_previous = SnapshotState(
            previous_domains, previous_known, dict(self.previous.metrics)
        )
        current = SnapshotState(current_domains, current_known, current.metrics)
        self.baseline = SnapshotState(
            baseline_domains, baseline_known, dict(self.baseline.metrics)
        )
        latest = compare_states(comparable_previous, current)
        now = datetime.now(timezone.utc).isoformat()
        for domain, counts in latest["domains"].items():
            for action in ("added", "removed"):
                count = int(counts[action])
                if count:
                    self.events.append(
                        {
                            "timestamp": now,
                            "domain": domain,
                            "kind": action,
                            "label": f"{count} {('device' if domain == 'devices' else DOMAIN_LABELS[domain])}{'s' if count != 1 else ''} {action}",
                        }
                    )
        self.events = self.events[-self.event_limit :]
        self.previous = current
        return compare_states(self.baseline, current), list(reversed(self.events))
