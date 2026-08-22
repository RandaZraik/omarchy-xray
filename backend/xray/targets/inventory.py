from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from xray.devices.pipewire import collect_pipewire
from xray.processes.collector import process_ancestor_map, process_parent_map
from xray.processes.identity import same_user_pids
from xray.runtime.context import list_windows
from xray.system.commands import CommandRunner
from xray.system.descriptors import DescriptorInventory, collect_descriptors
from xray.system.hyprland import visible_workspace_evidence
from xray.system.procfs import ProcFs
from xray.targets.query import TargetSpec


@dataclass(frozen=True)
class ResolutionInventory:
    windows: list[dict[str, object]]
    parents: dict[int, int]
    descriptors: DescriptorInventory | None = None
    visible_workspaces: frozenset[int] = frozenset()
    window_error: str = ""
    pipewire: list[dict[str, object]] | None = None
    pipewire_error: str = ""
    workspace_visibility_error: str = ""
    workspace_visibility_requested: bool = False
    same_user_pids: tuple[int, ...] | None = None
    parents_complete: bool = False


class InventoryCollector:
    """Collect only the shared evidence required to resolve one target kind."""

    GLOBAL_DISCOVERY_KINDS = frozenset(
        {"application", "port", "file", "device", "service"}
    )

    def __init__(self, proc: ProcFs, runner: CommandRunner) -> None:
        self.proc = proc
        self.runner = runner

    def collect(
        self,
        spec: TargetSpec,
        *,
        discover_resources: bool | None = None,
        include_visibility: bool = False,
    ) -> ResolutionInventory:
        if discover_resources is None:
            discover_resources = spec.kind in self.GLOBAL_DISCOVERY_KINDS
        pids = self.proc.pids() if discover_resources else []
        needs_same_user_pids = discover_resources and spec.kind in {
            "application",
            "port",
            "file",
            "device",
        }
        needs_descriptors = discover_resources and (
            spec.kind in {"port", "file"}
            or (spec.kind == "device" and spec.value == "gpu")
        )
        needs_pipewire = (
            discover_resources and spec.kind == "device" and spec.value != "gpu"
        )
        needs_visibility = include_visibility or spec.kind == "window-point"
        with ThreadPoolExecutor(
            max_workers=5, thread_name_prefix="xray-resolve"
        ) as pool:
            windows_future = pool.submit(list_windows, self.runner)
            visible_pids_future = (
                pool.submit(same_user_pids, self.proc, pids=pids)
                if needs_same_user_pids
                else None
            )
            parents_future = (
                pool.submit(process_parent_map, self.proc, pids)
                if discover_resources
                else None
            )
            pipewire_future = (
                pool.submit(collect_pipewire, self.runner) if needs_pipewire else None
            )
            visibility_future = (
                pool.submit(visible_workspace_evidence, self.runner)
                if needs_visibility
                else None
            )

            visible_pids = (
                visible_pids_future.result() if visible_pids_future is not None else []
            )
            descriptors_future = (
                pool.submit(collect_descriptors, self.proc, visible_pids)
                if needs_descriptors
                else None
            )
            windows, window_error = windows_future.result()
            parents = (
                parents_future.result()
                if parents_future is not None
                else process_ancestor_map(
                    self.proc,
                    [
                        *[int(window["pid"]) for window in windows],
                        *(
                            [int(spec.value)]
                            if spec.kind == "process" and spec.value.isdigit()
                            else []
                        ),
                    ],
                )
            )
            descriptors = (
                descriptors_future.result() if descriptors_future is not None else None
            )
            pipewire, pipewire_error = (
                pipewire_future.result() if pipewire_future is not None else (None, "")
            )
            visible_workspaces, workspace_visibility_error = (
                visibility_future.result()
                if visibility_future is not None
                else (set(), "")
            )
        return ResolutionInventory(
            windows=windows,
            parents=parents,
            parents_complete=discover_resources,
            same_user_pids=tuple(visible_pids),
            descriptors=descriptors,
            visible_workspaces=frozenset(visible_workspaces),
            window_error=window_error,
            pipewire=pipewire,
            pipewire_error=pipewire_error,
            workspace_visibility_error=workspace_visibility_error,
            workspace_visibility_requested=include_visibility
            or spec.kind == "window-point",
        )
