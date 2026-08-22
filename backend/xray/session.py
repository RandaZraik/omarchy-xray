from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import time

from xray import SCHEMA_VERSION
from xray.actions.desktop import DesktopEvidence
from xray.actions.process_control import ProcessActions, relaunch_plan
from xray.capsules.service import CapsuleService
from xray.config import LIMITS, TIMING, settings_contract, settings_defaults
from xray.evidence.changes import EvidenceHistory, unchanged
from xray.files.packages import PackageIndex
from xray.inspection.budget import constrain_snapshot
from xray.inspection.collector import SnapshotCollector
from xray.processes.identity import ProcessIdentity, identity_for
from xray.runtime.containers import ContainerInspector
from xray.runtime.systemd import SystemdInspector
from xray.system.commands import CommandRunner
from xray.system.hyprland import window_workspace_id
from xray.system.procfs import ProcFs
from xray.system.settings import SessionSettings, SettingsRepository
from xray.targets.catalog import TargetCatalog
from xray.targets.query import TargetSpec, parse_query
from xray.targets.resolver import ResolutionInventory, ResolvedTarget, TargetResolver


class InspectionSession:
    def __init__(
        self,
        proc: ProcFs | None = None,
        runner: CommandRunner | None = None,
        package_index: PackageIndex | None = None,
        settings_repository: SettingsRepository | None = None,
    ) -> None:
        self.proc = proc or ProcFs()
        self.runner = runner or CommandRunner(TIMING.command_seconds)
        self.packages = package_index or PackageIndex()
        self.systemd = SystemdInspector(self.proc, self.runner)
        self.containers = ContainerInspector(self.runner)
        self.resolver = TargetResolver(
            self.proc, self.runner, self.systemd, self.containers
        )
        self.target_catalog = TargetCatalog(
            self.proc, self.runner, self.systemd, self.containers
        )
        self.actions = ProcessActions(self.proc, self.runner)
        self.desktop = DesktopEvidence(self.runner)
        self.collector = SnapshotCollector(
            self.proc,
            self.runner,
            self.packages,
            self.actions,
            self.systemd,
            self.containers,
        )
        self.settings_repository = settings_repository or SettingsRepository()
        self.settings = SessionSettings(self.settings_repository.load())
        self.capsules = CapsuleService()
        self.history = EvidenceHistory(LIMITS.timeline_events)
        self.resolved: ResolvedTarget | None = None
        self.snapshot: dict[str, object] | None = None
        self.sampling_paused = False
        self._resolved_at = 0.0
        self._inspection_id = 0

    def bootstrap(self) -> dict[str, object]:
        return {
            "schema": SCHEMA_VERSION,
            "settings": self.settings.as_dict(),
            "settingsDefaults": settings_defaults(),
            "settingsSpec": settings_contract(),
            "capabilities": {
                "windowPicker": self.runner.available("slurp"),
                "windowPreview": self.runner.available("grim"),
                "pipewire": self.runner.available("pw-dump"),
                "journal": self.runner.available("journalctl"),
            },
        }

    def catalog(self) -> dict[str, object]:
        return self.target_catalog.collect()

    def inspect_focused(self) -> dict[str, object]:
        spec = TargetSpec("catalog", "", "Focused window")
        inventory = self.resolver.inventory(
            spec,
            discover_resources=False,
            include_visibility=True,
        )
        if inventory.workspace_visibility_error:
            return {}
        focused_window = next(
            (
                window
                for window in inventory.windows
                if window.get("focused")
                and window_workspace_id(window) in inventory.visible_workspaces
            ),
            None,
        )
        if not focused_window:
            return {}
        return self._inspect_spec(
            TargetSpec(
                "window",
                str(focused_window.get("address", "")),
                "Focused window",
            ),
            inventory=inventory,
        )

    def end_inspection(self) -> dict[str, object]:
        self.desktop.clear_previews()
        self.collector.reset_target()
        self.history = EvidenceHistory(LIMITS.timeline_events)
        self.resolved = None
        self.snapshot = None
        self.sampling_paused = False
        self._resolved_at = 0.0
        self._inspection_id += 1
        return {"closed": True}

    def configure(self, values: object) -> dict[str, object]:
        if not isinstance(values, dict):
            raise ValueError("settings must be an object")
        normalized = self.settings_repository.save(values)
        self.settings = SessionSettings(normalized)
        if not self.settings.capture_preview:
            self.desktop.clear_previews()
        return self.settings.as_dict()

    def inspect(self, query: object) -> dict[str, object]:
        return self._inspect_spec(parse_query(query))

    def focus_process(self, pid: object) -> dict[str, object]:
        if isinstance(pid, bool) or not (
            isinstance(pid, int) or isinstance(pid, str) and pid.isdigit()
        ):
            raise ValueError("pid must be a positive integer")
        try:
            normalized = int(pid)
        except (OverflowError, ValueError) as error:
            raise ValueError("pid must be an integer") from error
        if normalized <= 0:
            raise ValueError("pid must be a positive integer")
        return self._inspect_spec(
            TargetSpec("process", str(normalized), f"Process {normalized}")
        )

    def pick_window(self) -> dict[str, object]:
        point = self.desktop.pick_point()
        if not point:
            return {"cancelled": True}
        return self._inspect_spec(
            TargetSpec("window-point", f"{point[0]},{point[1]}", "Picked window")
        )

    def _inspect_spec(
        self,
        spec: TargetSpec,
        inventory: ResolutionInventory | None = None,
        resolved: ResolvedTarget | None = None,
    ) -> dict[str, object]:
        evidence = inventory or self.resolver.inventory(
            spec,
            include_visibility=self.settings.capture_preview,
        )
        target = resolved or self.resolver.resolve_with_inventory(spec, evidence)
        changed = (
            not self.resolved
            or target.root_pid != self.resolved.root_pid
            or target.spec != self.resolved.spec
        )
        self.resolved = target
        self._resolved_at = time.monotonic()
        if changed:
            self._inspection_id += 1
            self.collector.reset_target()
            self.history = EvidenceHistory(LIMITS.timeline_events)
        snapshot = self._collect(evidence)
        self.history.reset(snapshot)
        snapshot["changes"], snapshot["timeline"] = unchanged(), []
        snapshot = constrain_snapshot(snapshot)
        self.snapshot = snapshot
        return snapshot

    def refresh(self, compact: bool = False) -> dict[str, object]:
        if not self.resolved:
            raise ValueError("choose a target before refreshing")
        if self.sampling_paused and self.snapshot:
            paused = dict(self.snapshot)
            paused["samplingPaused"] = True
            paused["settings"] = self.settings.as_dict()
            return paused
        identity_matches = self._resolved_identity_matches()
        identity_replaced = self.resolved.root_pid > 0 and not identity_matches
        should_resolve = not identity_matches or (
            self.resolved.spec.kind != "application"
            and time.monotonic() - self._resolved_at >= TIMING.target_resolution_seconds
        )
        inventory = (
            self.resolver.inventory(
                self.resolved.spec,
                include_visibility=self.settings.capture_preview,
            )
            if should_resolve
            else None
        )
        if should_resolve:
            current = self.resolver.resolve_with_inventory(
                self.resolved.spec, inventory
            )
            if current.root_pid != self.resolved.root_pid or identity_replaced:
                if identity_replaced:
                    self.resolved = None
                return self._inspect_spec(current.spec, inventory, current)
            self.resolved = current
            self._resolved_at = time.monotonic()
        previous_snapshot = self.snapshot
        previous_resource_revision = self.collector.resource_revision
        snapshot = self._collect(inventory, refresh_resources=not compact)
        resources_reused = (
            previous_resource_revision == self.collector.resource_revision
        )
        previous_context = self.snapshot.get("context", {}) if self.snapshot else {}
        previous_preview = (
            previous_context.get("previewPath", "")
            if isinstance(previous_context, dict)
            else ""
        )
        previous_window = (
            previous_context.get("window", {})
            if isinstance(previous_context, dict)
            else {}
        )
        next_context = snapshot.get("context", {})
        next_window = (
            next_context.get("window", {}) if isinstance(next_context, dict) else {}
        )
        same_window = (
            isinstance(previous_window, dict)
            and isinstance(next_window, dict)
            and previous_window.get("address")
            and previous_window.get("address") == next_window.get("address")
        )
        if self.settings.capture_preview and previous_preview and same_window:
            context = dict(snapshot.get("context", {}))
            context["previewPath"] = previous_preview
            context["previewStatus"] = "ready"
            context["previewError"] = ""
            snapshot["context"] = context
        stable_domains = (
            ("connections", "files", "pipewire", "inhibitors", "runtime")
            if resources_reused
            else ()
        )
        snapshot["changes"], timeline = self.history.track(snapshot, stable_domains)
        snapshot["timeline"] = self._timeline_window(timeline)
        snapshot = constrain_snapshot(snapshot)
        self.snapshot = snapshot
        return (
            {"snapshotPatch": self._snapshot_patch(previous_snapshot, snapshot)}
            if compact and previous_snapshot
            else snapshot
        )

    def _resolved_identity_matches(self) -> bool:
        if not self.resolved or not self.snapshot or self.resolved.root_pid <= 0:
            return False
        root = self._root_process()
        if not root:
            return False
        expected = ProcessIdentity.from_row(root)
        return identity_for(self.proc, self.resolved.root_pid) == expected

    def reset_baseline(self) -> dict[str, object]:
        if not self.snapshot:
            raise ValueError("choose a target before resetting the baseline")
        self.history.reset(self.snapshot)
        self.snapshot["changes"], self.snapshot["timeline"] = unchanged(), []
        return self.snapshot

    def set_sampling_paused(self, paused: object) -> dict[str, object]:
        if not isinstance(paused, bool):
            raise ValueError("paused must be a boolean")
        next_state = paused
        if next_state != self.sampling_paused:
            self.collector.reset_sampling_baselines()
        self.sampling_paused = next_state
        if self.snapshot is not None:
            self.snapshot["samplingPaused"] = self.sampling_paused
        return {"samplingPaused": self.sampling_paused}

    def perform_action(
        self, action: object, expected_inspection_id: object = None
    ) -> dict[str, object]:
        if not self.snapshot or not self.resolved or self.resolved.root_pid <= 0:
            raise ValueError("choose a running target before using actions")
        if (
            not isinstance(expected_inspection_id, int)
            or isinstance(expected_inspection_id, bool)
            or expected_inspection_id != self._inspection_id
        ):
            return {
                "ok": False,
                "message": "The inspected target changed; review it before using this action",
            }
        if not isinstance(action, str):
            raise ValueError("action must be a string")
        action_id = action
        if action_id in {"pause", "resume", "terminate", "relaunch"}:
            if not self._resolved_identity_matches():
                return {
                    "ok": False,
                    "message": "The target process changed; inspect it again before using this action",
                }
            inventory = self.resolver.inventory(
                self.resolved.spec,
                discover_resources=True,
                include_visibility=False,
            )
            current = self.resolver.resolve_with_inventory(
                self.resolved.spec, inventory
            )
            if current.root_pid != self.resolved.root_pid:
                return {
                    "ok": False,
                    "message": "The selected process changed; inspect it again before using this action",
                }
            self.resolved = current
            self._resolved_at = time.monotonic()
        root = self._root_process()
        if not root:
            raise ValueError("the target process is no longer available")
        identity = ProcessIdentity.from_row(root)
        context = dict(self.snapshot.get("context", {}))
        if action_id == "relaunch":
            fresh_context = dict(self._collect(inventory).get("context", {}))
            if relaunch_plan(fresh_context) != relaunch_plan(context):
                return {
                    "ok": False,
                    "message": "The target manager changed; inspect it again before restarting",
                }
            context = fresh_context
        if (
            action_id in {"terminate", "relaunch"}
            and identity_for(self.proc, identity.pid) != identity
        ):
            return {
                "ok": False,
                "message": "The target process changed; inspect it again before using this action",
            }
        result = self.actions.perform(
            action_id,
            identity,
            context,
        )
        if action_id == "relaunch" and result.ok:
            self.systemd.invalidate()
            self.containers.invalidate()
            self.collector.reset_target()
            if result.reinspect_query:
                self.resolved = replace(
                    self.resolved, spec=parse_query(result.reinspect_query)
                )
            self._resolved_at = 0.0
        return result.as_dict()

    def _root_process(self) -> dict[str, object] | None:
        if not self.snapshot or not self.resolved:
            return None
        processes = self.snapshot.get("processes", [])
        if not isinstance(processes, list):
            return None
        return next(
            (
                row
                for row in processes
                if isinstance(row, dict) and row.get("pid") == self.resolved.root_pid
            ),
            None,
        )

    def export(self, directory: object = None) -> dict[str, object]:
        if not self.snapshot:
            raise ValueError("choose a target before exporting")
        return self.capsules.export(self.snapshot, directory)

    def open_capsule(self, path: object) -> dict[str, object]:
        return self.capsules.open(path)

    def compare_with_capsule(self, path: object) -> dict[str, object]:
        if not self.snapshot:
            raise ValueError("choose a target before comparing")
        return self.capsules.compare(self.snapshot, path)

    def report(self) -> dict[str, object]:
        if not self.snapshot:
            raise ValueError("choose a target before copying a report")
        return self.capsules.report(self.snapshot)

    def capture_preview(self) -> dict[str, object]:
        if not self.settings.capture_preview:
            return {"previewPath": "", "previewStatus": "disabled", "previewError": ""}
        if not self.snapshot:
            raise ValueError("choose a target before capturing a preview")
        context = dict(self.snapshot.get("context", {}))
        if context.get("previewEligible") is not True:
            return {
                "previewPath": "",
                "previewStatus": "unavailable",
                "previewError": str(
                    context.get("previewError", "Window preview is unavailable")
                ),
            }
        window = context.get("window", {})
        if not isinstance(window, dict) or not window:
            return {
                "previewPath": "",
                "previewStatus": "unavailable",
                "previewError": "No window is associated with this target",
            }
        capture = self.desktop.capture_window(window)
        context["previewPath"] = capture.path
        context["previewStatus"] = "ready" if capture.path else "failed"
        context["previewError"] = capture.error
        self.snapshot["context"] = context
        return {
            "previewPath": capture.path,
            "previewStatus": context["previewStatus"],
            "previewError": capture.error,
        }

    def _collect(
        self,
        inventory: ResolutionInventory | None = None,
        *,
        refresh_resources: bool = True,
    ) -> dict[str, object]:
        if self.resolved is None:
            raise ValueError("choose a target before collecting data")
        snapshot = self.collector.collect(
            self.resolved,
            self.settings.as_dict(),
            self.sampling_paused,
            inventory,
            refresh_resources=refresh_resources,
        )
        target = dict(snapshot.get("target", {}))
        target["inspectionId"] = self._inspection_id
        snapshot["target"] = target
        return snapshot

    @staticmethod
    def _snapshot_patch(
        previous: dict[str, object], current: dict[str, object]
    ) -> dict[str, object]:
        return {
            key: value for key, value in current.items() if previous.get(key) != value
        }

    def _timeline_window(
        self, timeline: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        cutoff = time.time() - self.settings.history_seconds
        result: list[dict[str, object]] = []
        for event in timeline:
            try:
                timestamp = datetime.fromisoformat(
                    str(event.get("timestamp", ""))
                ).timestamp()
            except ValueError:
                continue
            if timestamp >= cutoff:
                result.append(event)
        return result

    def close(self) -> None:
        self.desktop.close()
