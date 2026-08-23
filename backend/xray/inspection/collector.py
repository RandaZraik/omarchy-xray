from __future__ import annotations

from datetime import datetime, timezone
from xray import SCHEMA_VERSION
from xray.actions.process_control import ProcessActions
from xray.config import COVERAGE_DOMAINS, LIMITS
from xray.devices.gpu import GpuSampler, collect_gpu_clients
from xray.evidence.explanations import derive_explanations
from xray.files.packages import PackageIndex
from xray.inspection.coverage import build_coverage
from xray.inspection.resources import ResourceCollector
from xray.processes.activity import ActivitySampler
from xray.processes.collector import ProcessMetadataCache, collect_tree
from xray.processes.identity import ProcessIdentity, identity_for
from xray.runtime.containers import ContainerInspector
from xray.runtime.systemd import SystemdInspector
from xray.system.commands import CommandRunner
from xray.system.procfs import ProcFs
from xray.targets.query import canonical_query
from xray.targets.resolver import ResolutionInventory, ResolvedTarget


class SnapshotCollector:
    def __init__(
        self,
        proc: ProcFs,
        runner: CommandRunner,
        packages: PackageIndex,
        actions: ProcessActions,
        systemd: SystemdInspector,
        containers: ContainerInspector,
    ) -> None:
        self.proc = proc
        self.actions = actions
        self.resources = ResourceCollector(proc, runner, packages, systemd, containers)
        self.activity = ActivitySampler()
        self.process_metadata = ProcessMetadataCache()
        self.gpu = GpuSampler()

    def reset_target(self) -> None:
        self.activity = ActivitySampler()
        self.process_metadata = ProcessMetadataCache()
        self.gpu = GpuSampler()
        self.resources.reset()

    def reset_sampling_baselines(self) -> None:
        self.activity = ActivitySampler()
        self.gpu = GpuSampler()

    @property
    def resource_revision(self) -> int:
        return self.resources.revision

    def collect(
        self,
        resolved: ResolvedTarget,
        settings: dict[str, object],
        sampling_paused: bool,
        inventory: ResolutionInventory | None = None,
        *,
        refresh_resources: bool = True,
        identity_retry: bool = True,
    ) -> dict[str, object]:
        parent_map = (
            inventory.parents if inventory and inventory.parents_complete else None
        )
        generated_at = datetime.now(timezone.utc).isoformat()
        if resolved.root_pid <= 0:
            return self.empty_snapshot(
                resolved, settings, sampling_paused, generated_at
            )

        tree = collect_tree(
            self.proc,
            resolved.root_pid,
            LIMITS.process_tree,
            parent_map,
            self.process_metadata,
        )
        if not tree.root_identity or not tree.rows:
            return self.empty_snapshot(
                resolved,
                settings,
                sampling_paused,
                generated_at,
                "The selected process ended",
            )

        pids = [int(row["pid"]) for row in tree.rows]
        metrics = self.activity.sample(self.proc, tree.rows)
        resources = self.resources.collect(
            resolved,
            tree,
            inventory,
            force=refresh_resources,
        )
        connections = resources.connections.rows
        files = resources.files.rows
        locks = resources.files.locks
        pipewire = resources.devices.pipewire
        inhibitors = resources.devices.inhibitors
        context = dict(resources.runtime.context)
        security = resources.runtime.security
        gpu_clients, gpu_limited = collect_gpu_clients(
            self.proc, pids, resources.descriptors
        )
        metrics["gpuPercent"] = self.gpu.sample(gpu_clients)
        metrics["gpuAvailable"] = metrics["gpuPercent"] is not None
        uptime_seconds, uptime_limited = self.proc.process_uptime_seconds(
            tree.root_identity.start_time
        )
        changed_identities = self._changed_identities(tree.rows)
        if tree.root_identity.pid in changed_identities:
            self.reset_target()
            if identity_retry:
                return self.collect(
                    resolved,
                    settings,
                    sampling_paused,
                    None,
                    refresh_resources=True,
                    identity_retry=False,
                )
            failed = self.empty_snapshot(
                resolved,
                settings,
                sampling_paused,
                generated_at,
                "The process tree changed while X-Ray was reading it",
            )
            failed["target"] = {
                **failed["target"],
                "rootPid": resolved.root_pid,
                "ownerPid": resolved.owner_pid,
            }
            failed["coverage"]["limited"] = [
                "The selected process changed during inspection"
            ]
            failed["coverage"]["statusCode"] = "limited"
            failed["coverage"]["status"] = "Some data unavailable"
            return failed
        metrics["uptimeSeconds"] = uptime_seconds
        preview_requested = settings.get("capturePreview") is not False
        context["previewStatus"] = (
            "disabled"
            if not preview_requested
            else "pending"
            if context["previewEligible"]
            else "unavailable"
        )
        context["previewError"] = (
            ""
            if context["previewEligible"] or not preview_requested
            else "The window is not visible on an active workspace"
        )
        context["previewPath"] = ""
        coverage, device_availability = build_coverage(
            resolved=resolved,
            tree=tree,
            context=context,
            resources=resources,
            activity_limited=self.activity.last_limited,
            uptime_limited=uptime_limited,
            gpu_clients=gpu_clients,
            gpu_limited=gpu_limited,
        )
        descendant_churn = [
            pid for pid in changed_identities if pid != tree.root_identity.pid
        ]
        if descendant_churn:
            limitation = "Some child processes changed during inspection: " + ", ".join(
                str(pid) for pid in descendant_churn[:8]
            )
            coverage["limited"] = list(
                dict.fromkeys([*coverage.get("limited", []), limitation])
            )
            coverage["statusCode"] = "limited"
            coverage["status"] = "Some data unavailable"
            coverage["domains"]["processes"] = "limited"

        snapshot = self._snapshot_envelope(
            resolved, settings, sampling_paused, generated_at
        )
        snapshot.update(
            {
                "context": context,
                "metrics": metrics,
                "processes": tree.rows,
                "connections": connections,
                "files": files,
                "locks": locks,
                "devices": {
                    "pipewire": pipewire,
                    "gpu": gpu_clients,
                    "inhibitors": inhibitors,
                    "availability": device_availability,
                },
                "security": security,
                "logs": list(resources.runtime.logs),
                "coverage": coverage,
                "samplingPaused": sampling_paused,
                "settings": settings,
            }
        )
        snapshot["target"] = {
            **dict(snapshot["target"]),
            "label": self._target_label(resolved, context, tree.rows[0]),
            "rootPid": resolved.root_pid,
            "ownerPid": resolved.owner_pid,
        }
        root_state = str(tree.rows[0].get("state", ""))
        snapshot["actions"] = self.actions.catalog(
            tree.root_identity,
            context,
            paused=root_state in {"T", "t"},
            confirmation_target=f"{snapshot['target']['label']} · PID {resolved.root_pid}",
        )
        snapshot["explanations"] = derive_explanations(snapshot)
        return snapshot

    def _changed_identities(self, rows: list[dict[str, object]]) -> list[int]:
        return [
            int(row["pid"])
            for row in rows
            if identity_for(self.proc, int(row["pid"])) != ProcessIdentity.from_row(row)
        ]

    @staticmethod
    def empty_snapshot(
        resolved: ResolvedTarget,
        settings: dict[str, object],
        sampling_paused: bool,
        generated_at: str | None = None,
        error: str = "",
    ) -> dict[str, object]:
        return SnapshotCollector._snapshot_envelope(
            resolved,
            settings,
            sampling_paused,
            generated_at or datetime.now(timezone.utc).isoformat(),
            error,
        )

    @staticmethod
    def _snapshot_envelope(
        resolved: ResolvedTarget,
        settings: dict[str, object],
        sampling_paused: bool,
        generated_at: str,
        error: str = "",
    ) -> dict[str, object]:
        return {
            "schema": SCHEMA_VERSION,
            "generatedAt": generated_at,
            "target": {
                "kind": resolved.spec.kind,
                "value": resolved.spec.value,
                "query": canonical_query(
                    resolved.spec, resolved.window.get("address", "")
                ),
                "label": resolved.spec.label,
                "rootPid": 0,
                "ownerPid": 0,
                "trail": resolved.trail,
                "alternatives": resolved.alternatives,
                "error": error or resolved.error,
            },
            "context": {},
            "metrics": {},
            "processes": [],
            "connections": [],
            "files": [],
            "locks": [],
            "devices": {
                "pipewire": [],
                "gpu": [],
                "inhibitors": [],
                "availability": {
                    "pipewire": "unavailable",
                    "gpu": "unavailable",
                    "inhibitors": "unavailable",
                },
            },
            "security": {},
            "logs": [],
            "coverage": {
                "statusCode": "limited" if resolved.limited else "no-owner",
                "status": "Some data unavailable"
                if resolved.limited
                else "No matching process",
                "available": [],
                "limited": list(resolved.limited),
                "domains": {name: "unavailable" for name in COVERAGE_DOMAINS},
            },
            "actions": [],
            "explanations": [],
            "changes": {},
            "timeline": [],
            "samplingPaused": sampling_paused,
            "settings": settings,
        }

    @staticmethod
    def _target_label(
        resolved: ResolvedTarget,
        context: dict[str, object],
        root: dict[str, object],
    ) -> str:
        window = (
            context.get("window") if isinstance(context.get("window"), dict) else {}
        )
        return str(
            window.get("class")
            or window.get("title")
            or root.get("name")
            or resolved.spec.label
        )
