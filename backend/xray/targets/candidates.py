from __future__ import annotations

from pathlib import Path

from xray.config import LIMITS
from xray.devices.gpu import collect_gpu_clients
from xray.devices.pipewire import collect_pipewire, owners_for_device
from xray.files.open_files import owners_for_file
from xray.network.sockets import owners_for_port
from xray.processes.collector import process_name
from xray.processes.identity import same_user_pids
from xray.runtime.containers import ContainerInspector
from xray.runtime.systemd import SystemdInspector
from xray.system.commands import CommandRunner
from xray.system.procfs import ProcFs
from xray.targets.inventory import ResolutionInventory
from xray.targets.query import (
    TargetSpec,
    container_selector,
    match_score,
    rank_containers,
    rank_services,
    service_selector,
)


def ancestor_chain(
    parent_map: dict[int, int], pid: int, limit: int = LIMITS.ancestry_depth
) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    current = pid
    while current > 0 and current not in seen and len(result) < limit:
        seen.add(current)
        result.append(current)
        current = parent_map.get(current, 0)
    return result


class CandidateResolver:
    """Resolve target-kind evidence into ordered process ownership candidates."""

    def __init__(
        self,
        proc: ProcFs,
        runner: CommandRunner,
        systemd: SystemdInspector,
        containers: ContainerInspector,
    ) -> None:
        self.proc = proc
        self.runner = runner
        self.systemd = systemd
        self.containers = containers

    def resolve(
        self,
        spec: TargetSpec,
        inventory: ResolutionInventory,
    ) -> tuple[list[int], dict[str, object], list[str]]:
        handlers = {
            "process": self._process,
            "port": self._port,
            "file": self._file,
            "device": self._device,
            "service": self._service,
            "container": self._container,
            "application": self._application,
        }
        handler = handlers.get(spec.kind)
        if handler:
            return handler(spec, inventory)
        if spec.kind in {"window", "window-point"} and inventory.window_error:
            return [], {}, [inventory.window_error]
        return [], {}, []

    def absence_limitations(
        self,
        spec: TargetSpec,
        inventory: ResolutionInventory,
        candidate_limited: list[str],
    ) -> list[str]:
        if candidate_limited:
            return candidate_limited
        if spec.kind in {"window", "window-point", "application"}:
            return [inventory.window_error] if inventory.window_error else []
        if spec.kind in {"port", "file", "device"} and inventory.descriptors:
            return list(inventory.descriptors.limited)
        return []

    @staticmethod
    def empty_message(spec: TargetSpec) -> str:
        return {
            "port": f"No same-user process owns port {spec.value}",
            "file": "No same-user process currently has this file open",
            "device": f"No active same-user {spec.value} client was found",
            "process": "That process is no longer running",
            "application": "No running application matches this search",
            "service": "No running service matches this search",
            "container": "No running container matches this search",
            "window-point": "No window was found at that point",
            "window": "That window is no longer available",
        }.get(spec.kind, "No matching process was found")

    @staticmethod
    def _process(
        spec: TargetSpec, _inventory: ResolutionInventory
    ) -> tuple[list[int], dict[str, object], list[str]]:
        return [int(spec.value)], {}, []

    def _port(
        self, spec: TargetSpec, inventory: ResolutionInventory
    ) -> tuple[list[int], dict[str, object], list[str]]:
        pids, limited = owners_for_port(
            self.proc,
            int(spec.value),
            inventory.descriptors,
            (
                list(inventory.same_user_pids)
                if inventory.same_user_pids is not None
                else None
            ),
        )
        return pids, {}, limited

    def _file(
        self, spec: TargetSpec, inventory: ResolutionInventory
    ) -> tuple[list[int], dict[str, object], list[str]]:
        return (
            owners_for_file(self.proc, Path(spec.value), inventory.descriptors),
            {},
            list(inventory.descriptors.limited) if inventory.descriptors else [],
        )

    def _device(
        self, spec: TargetSpec, inventory: ResolutionInventory
    ) -> tuple[list[int], dict[str, object], list[str]]:
        if spec.value == "gpu":
            clients, limited = collect_gpu_clients(
                self.proc,
                (
                    list(inventory.same_user_pids)
                    if inventory.same_user_pids is not None
                    else self.proc.pids()
                ),
                inventory.descriptors,
            )
            return sorted({int(client["pid"]) for client in clients}), {}, limited
        devices, error = (
            (inventory.pipewire, inventory.pipewire_error)
            if inventory.pipewire is not None
            else collect_pipewire(self.runner)
        )
        return owners_for_device(devices, spec.value), {}, [error] if error else []

    def _service(
        self, spec: TargetSpec, inventory: ResolutionInventory
    ) -> tuple[list[int], dict[str, object], list[str]]:
        scope, query = service_selector(spec.value)
        exact_unit = query.endswith((".service", ".scope"))
        rows, limited = self.systemd.catalog()
        matches = rank_services(rows, query, scope)
        exact = [row for row in matches if str(row.get("id", "")) == query]
        ambiguous = (
            "The service exists in both user and system scopes; use "
            "service:user: or service:system:"
        )
        if not scope and len(exact) > 1:
            return [], {}, [ambiguous]
        if exact:
            unit = exact[0]
        elif exact_unit:
            scopes = [scope] if scope else ["user", "system"]
            direct = [
                details
                for candidate_scope in scopes
                if (details := self.systemd.details(query, candidate_scope))
            ]
            if not scope and len(direct) > 1:
                return [], {}, [ambiguous]
            if not direct:
                return [], {}, limited
            unit = direct[0]
        elif matches:
            unit = matches[0]
        else:
            return [], {}, limited
        identifier = str(unit["id"])
        scope = str(unit.get("scope", scope))
        details, detail_limited = self.systemd.details_with_evidence(identifier, scope)
        limited = list(dict.fromkeys([*limited, *detail_limited]))
        pids = self.systemd.pids(identifier, scope)
        main_pid = int(details.get("mainPid", 0)) if details else 0
        members = set(pids)
        roots = [pid for pid in pids if inventory.parents.get(pid, 0) not in members]
        main_root = next(
            (
                pid
                for pid in ancestor_chain(inventory.parents, main_pid)
                if pid in roots
            ),
            0,
        )
        primary = main_root or (
            roots[0] if roots else main_pid if main_pid in members else 0
        )
        if primary:
            pids = [primary, *[pid for pid in pids if pid != primary]]
        if len(roots) > 1:
            limited.append(
                "The systemd unit has multiple process roots; X-Ray shows the primary tree"
            )
        return pids, {"service": details} if details else {}, limited

    def _container(
        self, spec: TargetSpec, _inventory: ResolutionInventory
    ) -> tuple[list[int], dict[str, object], list[str]]:
        runtime, query = container_selector(spec.value)
        if runtime:
            details, limited = self.containers.details_with_evidence(query, runtime)
            pid, ownership_error = self._local_container_pid(details)
            return (
                [pid] if pid > 0 else [],
                {"container": details} if details else {},
                list(
                    dict.fromkeys(
                        [*limited, *([ownership_error] if ownership_error else [])]
                    )
                ),
            )
        rows, limited = self.containers.catalog()
        matches = rank_containers(rows, query)
        if len(matches) > 1:
            return (
                [],
                {},
                [
                    *limited,
                    "Multiple containers match; choose the runtime-qualified search result",
                ],
            )
        selected = matches[0] if matches else {}
        details, detail_limited = (
            self.containers.details_with_evidence(
                str(selected["id"]), str(selected["runtime"])
            )
            if selected
            else ({}, [])
        )
        pid, ownership_error = self._local_container_pid(details)
        return (
            [pid] if pid > 0 else [],
            {"container": details} if details else {},
            list(
                dict.fromkeys(
                    [
                        *limited,
                        *detail_limited,
                        *([ownership_error] if ownership_error else []),
                    ]
                )
            ),
        )

    def _local_container_pid(self, details: dict[str, object]) -> tuple[int, str]:
        if not details:
            return 0, ""
        try:
            pid = int(details.get("pid", 0))
        except (TypeError, ValueError):
            pid = 0
        identifier = str(details.get("id", "")).lower()
        cgroup = self.proc.read(pid, "cgroup", limit=131_072) if pid > 0 else None
        if (
            pid <= 0
            or len(identifier) < 12
            or not cgroup
            or not cgroup.available
            or identifier[:12] not in cgroup.value.lower()
        ):
            return (
                0,
                "The container runtime PID could not be tied to a local container cgroup",
            )
        return pid, ""

    def _application(
        self, spec: TargetSpec, inventory: ResolutionInventory
    ) -> tuple[list[int], dict[str, object], list[str]]:
        limited = [inventory.window_error] if inventory.window_error else []
        return (
            self._application_matches(
                spec.value,
                inventory.windows,
                (
                    list(inventory.same_user_pids)
                    if inventory.same_user_pids is not None
                    else None
                ),
            ),
            {},
            limited,
        )

    def _application_matches(
        self,
        query: str,
        windows: list[dict[str, object]],
        visible_pids: list[int] | None = None,
    ) -> list[int]:
        needle = query.casefold()
        scored: list[tuple[int, int]] = []
        for window in windows:
            score = match_score(
                needle,
                [str(window.get("class", "")), str(window.get("title", ""))],
            )
            if score:
                scored.append(
                    (score + (10 if window.get("focused") else 0), int(window["pid"]))
                )
        for pid in (
            visible_pids if visible_pids is not None else same_user_pids(self.proc)
        ):
            label = process_name(self.proc, pid).casefold()
            score = (
                80
                if label == needle
                else 50
                if label.startswith(needle)
                else 20
                if needle in label
                else 0
            )
            if score:
                scored.append((score, pid))
        seen: set[int] = set()
        result: list[int] = []
        for _score, pid in sorted(scored, key=lambda item: (-item[0], item[1])):
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result
