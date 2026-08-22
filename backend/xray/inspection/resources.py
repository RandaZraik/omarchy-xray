from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time

from xray.config import LIMITS, TIMING
from xray.devices.inhibitors import collect_inhibitors
from xray.devices.pipewire import collect_pipewire
from xray.files.open_files import collect_open_files
from xray.files.packages import PackageIndex
from xray.network.sockets import collect_connections
from xray.processes.identity import ProcessIdentity
from xray.processes.collector import ProcessCollection
from xray.runtime.causality import build_cause_chain
from xray.runtime.context import authoritative_window, collect_context
from xray.runtime.containers import ContainerInspector
from xray.runtime.security import collect_logs, collect_security
from xray.runtime.systemd import SystemdInspector
from xray.system.commands import CommandRunner
from xray.system.descriptors import DescriptorInventory, collect_descriptors
from xray.system.hyprland import window_workspace_id
from xray.system.procfs import ProcFs
from xray.targets.resolver import ResolutionInventory, ResolvedTarget


@dataclass(frozen=True)
class ConnectionEvidence:
    rows: list[dict[str, object]]
    limited: tuple[str, ...]


@dataclass(frozen=True)
class FileEvidence:
    rows: list[dict[str, object]]
    locks: list[dict[str, object]]
    limited: tuple[str, ...]
    files_complete: bool
    locks_available: bool


@dataclass(frozen=True)
class DeviceEvidence:
    pipewire: list[dict[str, object]]
    pipewire_error: str
    inhibitors: list[dict[str, object]]
    inhibitor_error: str


@dataclass(frozen=True)
class RuntimeEvidence:
    context: dict[str, object]
    context_limited: tuple[str, ...]
    limited: tuple[str, ...]
    security: dict[str, object]
    security_limited: tuple[str, ...]
    logs: tuple[dict[str, str], ...]
    logs_limited: str


@dataclass(frozen=True)
class ResourceEvidence:
    process_identities: tuple[ProcessIdentity, ...]
    collected_at: float
    descriptors: DescriptorInventory
    connections: ConnectionEvidence
    files: FileEvidence
    devices: DeviceEvidence
    runtime: RuntimeEvidence


class ResourceCollector:
    """Collect and briefly cache evidence that changes slower than live metrics."""

    def __init__(
        self,
        proc: ProcFs,
        runner: CommandRunner,
        packages: PackageIndex,
        systemd: SystemdInspector,
        containers: ContainerInspector,
    ) -> None:
        self.proc = proc
        self.runner = runner
        self.packages = packages
        self.systemd = systemd
        self.containers = containers
        self.reset()

    def reset(self) -> None:
        self._revision = 0
        self._cached: ResourceEvidence | None = None
        self._logs: list[dict[str, str]] = []
        self._logs_limited = ""
        self._logs_at = 0.0
        self._logs_identity: ProcessIdentity | None = None
        self._logs_scope = ""
        self._security: dict[str, object] = {}
        self._security_limited: list[str] = []
        self._security_at = 0.0
        self._security_identity: ProcessIdentity | None = None

    def collect(
        self,
        resolved: ResolvedTarget,
        processes: ProcessCollection,
        inventory: ResolutionInventory | None,
        *,
        force: bool,
    ) -> ResourceEvidence:
        now = time.monotonic()
        rows = processes.rows
        root_identity = processes.root_identity
        if root_identity is None or not rows:
            raise ValueError("resource collection requires a rooted process tree")
        pids = [int(row["pid"]) for row in rows]
        process_identities = tuple(ProcessIdentity.from_row(row) for row in rows)
        if (
            not force
            and self._cached
            and self._cached.process_identities == process_identities
            and now - self._cached.collected_at < TIMING.resource_refresh_seconds
        ):
            return self._cached

        windows = inventory.windows if inventory else None
        pipewire_rows = inventory.pipewire if inventory else None
        pipewire_error = inventory.pipewire_error if inventory else ""
        context_rows = (
            [rows[0]]
            if resolved.spec.kind == "process" and not resolved.window
            else rows
        )
        with ThreadPoolExecutor(
            max_workers=6, thread_name_prefix="xray-evidence"
        ) as pool:
            descriptor_future = pool.submit(collect_descriptors, self.proc, pids)
            inhibitor_future = pool.submit(collect_inhibitors, self.runner, pids)
            context_future = pool.submit(
                collect_context,
                self.proc,
                rows[0],
                context_rows,
                self.runner,
                self.packages,
                windows,
            )
            security_future = pool.submit(self._collect_security, root_identity)
            pipewire_future = (
                pool.submit(collect_pipewire, self.runner, pids)
                if pipewire_rows is None
                else None
            )

            descriptors = descriptor_future.result()
            connections_future = pool.submit(
                collect_connections, self.proc, pids, descriptors
            )
            files_future = pool.submit(
                collect_open_files,
                self.proc,
                pids,
                limit_per_process=LIMITS.descriptors_per_process,
                inventory=descriptors,
            )

            context, context_limited = context_future.result()
            context["window"] = authoritative_window(
                context.get("window"), resolved.window
            )
            context["previewEligible"] = self._preview_eligible(context, inventory)
            runtime_limited: list[str] = []
            service, container = self._runtime_context(
                resolved, context, runtime_limited
            )
            context["service"] = service
            context["container"] = container
            context["cause"] = build_cause_chain(
                self.proc, resolved.owner_pid, service, container
            )
            self._refresh_logs(root_identity, pids, service)

            connections, connection_limited = connections_future.result()
            file_evidence = files_future.result()
            inhibitors, inhibitor_error = inhibitor_future.result()
            security, security_limited = security_future.result()
            if pipewire_future is not None:
                pipewire, pipewire_error = pipewire_future.result()
            else:
                selected_pids = set(pids)
                pipewire = [
                    row
                    for row in pipewire_rows or []
                    if int(row.get("pid", 0)) in selected_pids
                ]
        self._revision += 1
        self._cached = ResourceEvidence(
            process_identities=process_identities,
            collected_at=now,
            descriptors=descriptors,
            connections=ConnectionEvidence(connections, tuple(connection_limited)),
            files=FileEvidence(
                rows=file_evidence.rows,
                locks=file_evidence.locks,
                limited=file_evidence.limited,
                files_complete=file_evidence.files_complete,
                locks_available=file_evidence.locks_available,
            ),
            devices=DeviceEvidence(
                pipewire=pipewire,
                pipewire_error=pipewire_error,
                inhibitors=inhibitors,
                inhibitor_error=inhibitor_error,
            ),
            runtime=RuntimeEvidence(
                context=context,
                context_limited=tuple(context_limited),
                limited=tuple(runtime_limited),
                security=security,
                security_limited=tuple(security_limited),
                logs=tuple(self._logs),
                logs_limited=self._logs_limited,
            ),
        )
        return self._cached

    @property
    def revision(self) -> int:
        return self._revision

    def _preview_eligible(
        self, context: dict[str, object], inventory: ResolutionInventory | None
    ) -> bool:
        window = context.get("window", {})
        if not isinstance(window, dict):
            return False
        if (
            not window.get("mapped", True)
            or window.get("hidden", False)
            or not window.get("focused", False)
        ):
            return False
        if inventory:
            return window_workspace_id(window) in inventory.visible_workspaces
        cached_window = (
            self._cached.runtime.context.get("window", {}) if self._cached else {}
        )
        return bool(
            isinstance(cached_window, dict)
            and cached_window.get("address") == window.get("address")
            and self._cached
            and self._cached.runtime.context.get("previewEligible")
        )

    def _runtime_context(
        self,
        resolved: ResolvedTarget,
        context: dict[str, object],
        limited: list[str],
    ) -> tuple[dict[str, object], dict[str, object]]:
        metadata = resolved.metadata if isinstance(resolved.metadata, dict) else {}
        service = metadata.get("service", {})
        if not isinstance(service, dict) or not service:
            service, service_limited = self.systemd.for_process_with_evidence(
                resolved.owner_pid
            )
            limited.extend(service_limited)
        container = metadata.get("container", {})
        if not isinstance(container, dict) or not container:
            launch = context.get("launch", {})
            container_id = (
                str(launch.get("container", "")) if isinstance(launch, dict) else ""
            )
            container, container_limited = self.containers.for_cgroup_with_evidence(
                container_id
            )
            limited.extend(container_limited)
        return service, container

    def _refresh_logs(
        self,
        identity: ProcessIdentity,
        pids: list[int],
        service: dict[str, object] | None = None,
    ) -> None:
        now = time.monotonic()
        scope = str((service or {}).get("scope", "")) or "user"
        if (
            self._logs_identity == identity
            and self._logs_scope == scope
            and self._logs_at
            and now - self._logs_at < TIMING.journal_refresh_seconds
        ):
            return
        started_at, start_error = self.proc.process_started_at(identity.start_time)
        if start_error:
            self._logs = []
            self._logs_limited = start_error
        else:
            self._logs, self._logs_limited = collect_logs(
                self.runner,
                identity.pid,
                started_at,
                LIMITS.journal_entries,
                scope,
                pids,
                str((service or {}).get("id", "")),
            )
        self._logs_at = now
        self._logs_identity = identity
        self._logs_scope = scope

    def _collect_security(
        self, identity: ProcessIdentity
    ) -> tuple[dict[str, object], list[str]]:
        now = time.monotonic()
        if (
            self._security_identity != identity
            or not self._security_at
            or now - self._security_at >= TIMING.security_refresh_seconds
        ):
            self._security, self._security_limited = collect_security(
                self.proc, identity.pid
            )
            self._security_identity = identity
            self._security_at = now
        return self._security, self._security_limited
