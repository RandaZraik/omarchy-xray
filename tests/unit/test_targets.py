from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from xray.system.procfs import ProcFs
from xray.targets.query import TargetSpec
from xray.targets.resolver import (
    ResolutionInventory,
    TargetResolver,
    ancestor_chain,
    app_root_for_pid,
)
from support.procfs import write_process as write_proc_process


def write_process(root: Path, pid: int, name: str, ppid: int, cgroup: str = "") -> None:
    write_proc_process(root, pid, name, ppid, cgroup=cgroup)


class TargetResolverTests(unittest.TestCase):
    def test_device_resolution_reuses_one_pipewire_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 41, "recorder", 1)
            resolver = TargetResolver(ProcFs(root), MagicMock())
            spec = TargetSpec("device", "microphone", "Microphone")
            rows = [
                {
                    "id": 7,
                    "pid": 41,
                    "kind": "microphone",
                    "active": True,
                }
            ]
            with (
                patch("xray.targets.inventory.list_windows", return_value=([], "")),
                patch(
                    "xray.targets.inventory.collect_pipewire", return_value=(rows, "")
                ) as pipewire,
            ):
                inventory = resolver.inventory(spec)
                resolved = resolver.resolve_with_inventory(spec, inventory)

        self.assertEqual(resolved.owner_pid, 41)
        self.assertIs(inventory.pipewire, rows)
        pipewire.assert_called_once()

    def test_monitor_visibility_is_collected_only_when_it_is_needed(self) -> None:
        with TemporaryDirectory() as directory:
            resolver = TargetResolver(ProcFs(Path(directory)), MagicMock())
            with (
                patch("xray.targets.inventory.list_windows", return_value=([], "")),
                patch(
                    "xray.targets.inventory.visible_workspace_evidence",
                    return_value=({2}, ""),
                ) as visible,
                patch("xray.targets.inventory.same_user_pids") as same_user,
            ):
                ordinary = resolver.inventory(
                    TargetSpec("process", "41", "Process 41"),
                    discover_resources=False,
                )
                preview = resolver.inventory(
                    TargetSpec("process", "41", "Process 41"),
                    discover_resources=False,
                    include_visibility=True,
                )

        self.assertEqual(ordinary.visible_workspaces, frozenset())
        self.assertEqual(preview.visible_workspaces, frozenset({2}))
        visible.assert_called_once()
        same_user.assert_not_called()

    def test_app_root_uses_nearest_window_ancestor(self) -> None:
        windows = [{"pid": 20, "focused": True, "title": "Editor"}]
        root, window = app_root_for_pid(22, windows, {22: 21, 21: 20, 20: 1})
        self.assertEqual(root, 20)
        self.assertEqual(window["title"], "Editor")

    def test_app_root_can_keep_parent_with_descendant_window(self) -> None:
        windows = [{"pid": 31, "focused": False, "title": "Browser"}]
        root, window = app_root_for_pid(30, windows, {31: 30, 30: 1})
        self.assertEqual(root, 30)
        self.assertEqual(window["pid"], 31)

    def test_explicit_process_does_not_attach_an_unrelated_descendant_window(
        self,
    ) -> None:
        windows = [{"pid": 31, "focused": True, "title": "Browser"}]
        root, window = app_root_for_pid(
            1, windows, {31: 30, 30: 1}, allow_descendant_window=False
        )
        self.assertEqual(root, 1)
        self.assertEqual(window, {})

    def test_app_root_prefers_the_focused_sibling_window(self) -> None:
        windows = [
            {"pid": 20, "focused": False, "title": "Background"},
            {"pid": 20, "focused": True, "title": "Focused"},
        ]
        root, window = app_root_for_pid(20, windows, {20: 1})
        self.assertEqual(root, 20)
        self.assertEqual(window["title"], "Focused")

    def test_explicit_process_keeps_its_own_subtree_below_a_windowed_parent(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 20, "terminal", 1)
            write_process(root, 21, "worker", 20)
            resolved = TargetResolver(ProcFs(root), MagicMock()).resolve_with_inventory(
                TargetSpec("process", "21", "Process 21"),
                ResolutionInventory(
                    [{"pid": 20, "focused": True, "title": "Terminal"}],
                    {20: 1, 21: 20},
                ),
            )

        self.assertEqual(resolved.owner_pid, 21)
        self.assertEqual(resolved.root_pid, 21)
        self.assertEqual(resolved.window["pid"], 20)

    def test_ancestor_chain_is_cycle_safe(self) -> None:
        self.assertEqual(ancestor_chain({4: 5, 5: 4}, 4), [4, 5])

    def test_exact_window_query_keeps_address_and_workspace_with_sibling_windows(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 40, "multi-window", 1)
            resolver = TargetResolver(ProcFs(root), MagicMock())
            windows = [
                {
                    "pid": 40,
                    "address": "0x1",
                    "workspace": {"id": 1},
                    "focused": True,
                    "title": "First",
                },
                {
                    "pid": 40,
                    "address": "0x2",
                    "workspace": {"id": 2},
                    "focused": False,
                    "title": "Second",
                },
            ]
            resolved = resolver.resolve_with_inventory(
                TargetSpec("window", "0x2", "Selected window"),
                ResolutionInventory(windows, {40: 1}),
            )
        self.assertEqual(resolved.window["address"], "0x2")
        self.assertEqual(resolved.window["workspace"]["id"], 2)

    def test_point_picker_ignores_overlapping_windows_on_hidden_workspaces(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 40, "multi-window", 1)
            resolver = TargetResolver(ProcFs(root), MagicMock())
            windows = [
                {
                    "pid": 40,
                    "address": "0x-hidden",
                    "workspace": {"id": 1},
                    "focused": False,
                    "focusOrder": 1,
                    "mapped": True,
                    "hidden": False,
                    "x": 100,
                    "y": 100,
                    "width": 800,
                    "height": 600,
                },
                {
                    "pid": 40,
                    "address": "0x-visible",
                    "workspace": {"id": 2},
                    "focused": True,
                    "focusOrder": 0,
                    "mapped": True,
                    "hidden": False,
                    "x": 100,
                    "y": 100,
                    "width": 800,
                    "height": 600,
                },
            ]
            resolved = resolver.resolve_with_inventory(
                TargetSpec("window-point", "200,200", "Picked window"),
                ResolutionInventory(windows, {40: 1}, None, frozenset({2})),
            )
        self.assertEqual(resolved.window["address"], "0x-visible")
        self.assertEqual(resolved.window["workspace"]["id"], 2)

    def test_point_picker_does_not_fall_back_to_a_hidden_workspace(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 40, "hidden-window", 1)
            resolver = TargetResolver(ProcFs(root), MagicMock())
            windows = [
                {
                    "pid": 40,
                    "address": "0x-hidden",
                    "workspace": {"id": 1},
                    "mapped": True,
                    "hidden": False,
                    "x": 100,
                    "y": 100,
                    "width": 800,
                    "height": 600,
                }
            ]
            resolved = resolver.resolve_with_inventory(
                TargetSpec("window-point", "200,200", "Picked window"),
                ResolutionInventory(windows, {40: 1}, None, frozenset({2})),
            )

        self.assertEqual(resolved.root_pid, 0)
        self.assertEqual(resolved.window, {})

    def test_point_picker_fails_closed_when_workspace_visibility_is_unknown(
        self,
    ) -> None:
        resolved = TargetResolver(
            ProcFs(Path("/missing")), MagicMock()
        ).resolve_with_inventory(
            TargetSpec("window-point", "200,200", "Picked window"),
            ResolutionInventory(
                [
                    {
                        "pid": 40,
                        "address": "0x-unknown",
                        "workspace": {"id": 1},
                        "mapped": True,
                        "hidden": False,
                        "x": 100,
                        "y": 100,
                        "width": 800,
                        "height": 600,
                    }
                ],
                {40: 1},
                workspace_visibility_error="Hyprland monitor visibility is unavailable",
            ),
        )

        self.assertEqual(resolved.root_pid, 0)
        self.assertIn("visibility is unavailable", resolved.limited[0])

    def test_service_and_container_queries_keep_exact_runtime_metadata(self) -> None:
        class Services:
            def catalog(self):
                return [{"id": "demo.service", "scope": "user"}], []

            def pids(self, _unit, _scope):
                return [41]

            def details(self, _unit, _scope):
                return {"id": "demo.service", "scope": "user", "mainPid": 41}

            def details_with_evidence(self, unit, scope):
                return self.details(unit, scope), []

        class Containers:
            def catalog(self):
                return [
                    {
                        "id": "abcdef1234567890",
                        "shortId": "abcdef123456",
                        "name": "db",
                        "runtime": "docker",
                    }
                ], []

            def details(self, _identifier, _runtime):
                return {
                    "id": "abcdef1234567890",
                    "name": "db",
                    "runtime": "docker",
                    "pid": 42,
                }

            def details_with_evidence(self, identifier, runtime):
                return self.details(identifier, runtime), []

        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 41, "service", 1)
            write_process(
                root,
                42,
                "container",
                1,
                "0::/system.slice/docker-abcdef1234567890.scope\n",
            )
            resolver = TargetResolver(
                ProcFs(root), MagicMock(), Services(), Containers()
            )
            inventory = ResolutionInventory([], {41: 1, 42: 1})
            service = resolver.resolve_with_inventory(
                TargetSpec("service", "demo", "Demo"), inventory
            )
            container = resolver.resolve_with_inventory(
                TargetSpec("container", "db", "DB"), inventory
            )
        self.assertEqual(service.metadata["service"]["mainPid"], 41)
        self.assertEqual(container.metadata["container"]["runtime"], "docker")

    def test_exact_service_and_container_resolution_do_not_depend_on_catalog_caps(
        self,
    ) -> None:
        class Services:
            def catalog(self):
                return [], ["Service catalog is limited"]

            def details(self, unit, scope):
                if unit == "beyond-cap.service" and scope == "user":
                    return {
                        "id": unit,
                        "scope": scope,
                        "mainPid": 41,
                    }
                return {}

            def details_with_evidence(self, unit, scope):
                return self.details(unit, scope), []

            def pids(self, _unit, _scope):
                return [41]

        class Containers:
            def catalog(self):
                return [], ["Container catalog is limited"]

            def details_with_evidence(self, identifier, runtime=""):
                if identifier == "beyond-cap":
                    return {
                        "id": "abcdef1234567890",
                        "runtime": "docker",
                        "pid": 42,
                    }, []
                return {}, []

        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 41, "service", 1)
            write_process(
                root,
                42,
                "container",
                1,
                "0::/system.slice/docker-abcdef1234567890.scope\n",
            )
            resolver = TargetResolver(
                ProcFs(root), MagicMock(), Services(), Containers()
            )
            inventory = ResolutionInventory([], {41: 1, 42: 1})
            service = resolver.resolve_with_inventory(
                TargetSpec("service", "user:beyond-cap.service", "Service"),
                inventory,
            )
            container = resolver.resolve_with_inventory(
                TargetSpec("container", "docker:beyond-cap", "Container"), inventory
            )

        self.assertEqual(service.root_pid, 41)
        self.assertEqual(container.root_pid, 42)

    def test_preview_visibility_failure_is_included_for_ordinary_targets(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 41, "app", 1)
            resolved = TargetResolver(ProcFs(root), MagicMock()).resolve_with_inventory(
                TargetSpec("process", "41", "Process 41"),
                ResolutionInventory(
                    [],
                    {41: 1},
                    workspace_visibility_error="Monitor visibility unavailable",
                    workspace_visibility_requested=True,
                ),
            )

        self.assertIn("Monitor visibility unavailable", resolved.limited)

    def test_service_prefers_main_pid_and_marks_sibling_roots_limited(self) -> None:
        class Services:
            def catalog(self):
                return [{"id": "demo.service", "scope": "user"}], []

            def pids(self, _unit, _scope):
                return [40, 41, 42]

            def details(self, _unit, _scope):
                return {"id": "demo.service", "scope": "user", "mainPid": 41}

            def details_with_evidence(self, unit, scope):
                return self.details(unit, scope), []

        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 40, "older-sibling", 1)
            write_process(root, 41, "main", 1)
            write_process(root, 42, "main-child", 41)
            resolver = TargetResolver(ProcFs(root), MagicMock(), Services())
            resolved = resolver.resolve_with_inventory(
                TargetSpec("service", "demo", "Demo"),
                ResolutionInventory([], {40: 1, 41: 1, 42: 41}),
            )

        self.assertEqual(resolved.root_pid, 41)
        self.assertIn("multiple process roots", resolved.limited[0])

    def test_service_uses_the_supervisor_root_that_contains_main_pid(self) -> None:
        class Services:
            def catalog(self):
                return [{"id": "demo.service", "scope": "user"}], []

            def pids(self, _unit, _scope):
                return [40, 41, 42]

            def details_with_evidence(self, _unit, _scope):
                return {"id": "demo.service", "scope": "user", "mainPid": 41}, []

        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 40, "supervisor", 1)
            write_process(root, 41, "main", 40)
            write_process(root, 42, "sibling", 40)
            resolved = TargetResolver(
                ProcFs(root), MagicMock(), Services()
            ).resolve_with_inventory(
                TargetSpec("service", "demo", "Demo"),
                ResolutionInventory([], {40: 1, 41: 40, 42: 40}),
            )

        self.assertEqual(resolved.root_pid, 40)
        self.assertFalse(
            any("multiple process roots" in row for row in resolved.limited)
        )

    def test_container_pid_must_match_a_local_container_cgroup(self) -> None:
        containers = MagicMock()
        containers.details_with_evidence.return_value = (
            {
                "id": "abcdef1234567890",
                "runtime": "docker",
                "pid": 42,
            },
            [],
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(
                root, 42, "unrelated-local-process", 1, "0::/user.slice/app.scope\n"
            )
            resolved = TargetResolver(
                ProcFs(root), MagicMock(), MagicMock(), containers
            ).resolve_with_inventory(
                TargetSpec("container", "docker:demo", "Demo"),
                ResolutionInventory([], {42: 1}),
            )

        self.assertEqual(resolved.root_pid, 0)
        self.assertIn("local container cgroup", resolved.limited[0])

    def test_unavailable_owner_evidence_is_not_reported_as_proven_absence(self) -> None:
        class Services:
            def catalog(self):
                return [], ["User service catalog is unavailable"]

        with TemporaryDirectory() as directory:
            resolver = TargetResolver(
                ProcFs(Path(directory)), MagicMock(), Services(), MagicMock()
            )
            resolved = resolver.resolve_with_inventory(
                TargetSpec("service", "missing", "Missing service"),
                ResolutionInventory([], {}),
            )

        self.assertEqual(resolved.root_pid, 0)
        self.assertIn("required system data is unavailable", resolved.error)
        self.assertEqual(resolved.limited, ("User service catalog is unavailable",))

    def test_ambiguous_service_scope_requires_an_explicit_scope(self) -> None:
        class Services:
            def catalog(self):
                return [
                    {"id": "demo.service", "scope": "system"},
                    {"id": "demo.service", "scope": "user"},
                ], []

        with TemporaryDirectory() as directory:
            resolver = TargetResolver(
                ProcFs(Path(directory)), MagicMock(), Services(), MagicMock()
            )
            resolved = resolver.resolve_with_inventory(
                TargetSpec("service", "demo.service", "Demo service"),
                ResolutionInventory([], {}),
            )

        self.assertEqual(resolved.root_pid, 0)
        self.assertIn("both user and system scopes", resolved.limited[0])


if __name__ == "__main__":
    unittest.main()
