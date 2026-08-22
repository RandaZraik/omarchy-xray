from __future__ import annotations

from dataclasses import dataclass
from xray.config import LIMITS
from xray.processes.collector import process_name
from xray.runtime.containers import ContainerInspector
from xray.runtime.systemd import SystemdInspector
from xray.system.commands import CommandRunner
from xray.system.procfs import ProcFs
from xray.targets.candidates import CandidateResolver, ancestor_chain
from xray.targets.inventory import InventoryCollector, ResolutionInventory
from xray.targets.query import TargetSpec


@dataclass(frozen=True)
class ResolvedTarget:
    spec: TargetSpec
    root_pid: int
    owner_pid: int
    window: dict[str, object]
    trail: list[dict[str, object]]
    alternatives: list[dict[str, object]]
    metadata: dict[str, object]
    error: str = ""
    limited: tuple[str, ...] = ()


def app_root_for_pid(
    pid: int,
    windows: list[dict[str, object]],
    parents: dict[int, int],
    *,
    allow_descendant_window: bool = True,
) -> tuple[int, dict[str, object]]:
    by_pid: dict[int, list[dict[str, object]]] = {}
    for window in windows:
        by_pid.setdefault(int(window["pid"]), []).append(window)
    for ancestor in ancestor_chain(parents, pid):
        if ancestor in by_pid:
            candidates = by_pid[ancestor]
            return ancestor, next(
                (window for window in candidates if window.get("focused")),
                candidates[0],
            )
    descendants = [
        window
        for window in windows
        if allow_descendant_window
        and pid in ancestor_chain(parents, int(window["pid"]))
    ]
    if descendants:
        focused = next(
            (window for window in descendants if window.get("focused")), descendants[0]
        )
        return pid, focused
    return pid, {}


def _trail(
    spec: TargetSpec,
    owner_pid: int,
    root_pid: int,
    window: dict[str, object],
    proc: ProcFs,
) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = [
        {"kind": spec.kind, "label": spec.label, "value": spec.value}
    ]
    if owner_pid > 0:
        steps.append(
            {
                "kind": "process",
                "label": process_name(proc, owner_pid),
                "value": owner_pid,
            }
        )
    if root_pid > 0 and root_pid != owner_pid:
        steps.append(
            {
                "kind": "application",
                "label": process_name(proc, root_pid),
                "value": root_pid,
            }
        )
    if window:
        steps.append(
            {
                "kind": "window",
                "label": window.get("title") or window.get("class") or "Window",
                "value": window.get("address", ""),
            }
        )
    return steps


def _alternatives(pids: list[int], proc: ProcFs) -> list[dict[str, object]]:
    return [
        {"pid": pid, "label": process_name(proc, pid)}
        for pid in pids[: LIMITS.query_matches]
    ]


class TargetResolver:
    def __init__(
        self,
        proc: ProcFs,
        runner: CommandRunner,
        systemd: SystemdInspector | None = None,
        containers: ContainerInspector | None = None,
    ) -> None:
        self.proc = proc
        self.runner = runner
        self.systemd = systemd or SystemdInspector(proc, runner)
        self.containers = containers or ContainerInspector(runner)
        self.inventory_collector = InventoryCollector(proc, runner)
        self.candidates = CandidateResolver(proc, runner, self.systemd, self.containers)

    def resolve(self, spec: TargetSpec) -> ResolvedTarget:
        inventory = self.inventory(spec)
        return self.resolve_with_inventory(spec, inventory)

    def inventory(
        self,
        spec: TargetSpec,
        *,
        discover_resources: bool | None = None,
        include_visibility: bool = False,
    ) -> ResolutionInventory:
        return self.inventory_collector.collect(
            spec,
            discover_resources=discover_resources,
            include_visibility=include_visibility,
        )

    def resolve_with_inventory(
        self, spec: TargetSpec, inventory: ResolutionInventory
    ) -> ResolvedTarget:
        windows = inventory.windows
        parents = inventory.parents
        selected_window = self._selected_window(
            spec,
            windows,
            inventory.visible_workspaces,
            inventory.workspace_visibility_error,
        )
        if selected_window:
            candidates, metadata, candidate_limited = (
                [int(selected_window["pid"])],
                {},
                [],
            )
        else:
            candidates, metadata, candidate_limited = self.candidates.resolve(
                spec, inventory
            )
        if spec.kind == "window-point" and inventory.workspace_visibility_error:
            candidates = []
            candidate_limited = [
                *candidate_limited,
                inventory.workspace_visibility_error,
            ]
        all_limited = list(
            dict.fromkeys(
                [
                    *([inventory.window_error] if inventory.window_error else []),
                    *(
                        [inventory.workspace_visibility_error]
                        if inventory.workspace_visibility_requested
                        and inventory.workspace_visibility_error
                        else []
                    ),
                    *(inventory.descriptors.limited if inventory.descriptors else ()),
                    *candidate_limited,
                ]
            )
        )
        if not candidates:
            absence_limited = self.candidates.absence_limitations(
                spec, inventory, candidate_limited
            )
            return ResolvedTarget(
                spec,
                0,
                0,
                {},
                [{"kind": spec.kind, "label": spec.label, "value": spec.value}],
                [],
                {},
                (
                    "No matching process could be found because required system data is unavailable"
                    if absence_limited
                    else self.candidates.empty_message(spec)
                ),
                tuple(absence_limited),
            )
        owner_pid = candidates[0]
        application_root, inferred_window = app_root_for_pid(
            owner_pid,
            windows,
            parents,
            allow_descendant_window=spec.kind != "process",
        )
        root_pid = owner_pid if spec.kind == "process" else application_root
        window = selected_window or inferred_window
        return ResolvedTarget(
            spec,
            root_pid,
            owner_pid,
            window,
            _trail(spec, owner_pid, root_pid, window, self.proc),
            _alternatives(candidates, self.proc),
            metadata,
            "",
            tuple(all_limited),
        )

    @staticmethod
    def _selected_window(
        spec: TargetSpec,
        windows: list[dict[str, object]],
        visible_workspaces: frozenset[int] = frozenset(),
        workspace_visibility_error: str = "",
    ) -> dict[str, object]:
        if spec.kind == "window":
            return next(
                (window for window in windows if window.get("address") == spec.value),
                {},
            )
        if spec.kind != "window-point":
            return {}
        if workspace_visibility_error:
            return {}
        x_text, _, y_text = spec.value.partition(",")
        try:
            x, y = int(x_text), int(y_text)
        except ValueError:
            return {}
        candidates = [
            window
            for window in windows
            if window.get("mapped", True)
            and not window.get("hidden", False)
            and int(window["x"]) <= x < int(window["x"]) + int(window["width"])
            and int(window["y"]) <= y < int(window["y"]) + int(window["height"])
        ]
        if visible_workspaces:
            candidates = [
                window
                for window in candidates
                if int((window.get("workspace") or {}).get("id", 0))
                in visible_workspaces
            ]
        candidates.sort(
            key=lambda window: (
                not bool(window.get("focused")),
                int(window.get("focusOrder", 1_000_000)),
            )
        )
        return candidates[0] if candidates else {}
