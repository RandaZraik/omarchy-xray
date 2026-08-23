from pathlib import Path
from threading import Event
import unittest
from unittest.mock import MagicMock, patch

from xray.config import LIMITS
from xray.system.procfs import ProcFs
from xray.system.descriptors import DescriptorInventory
from xray.targets.catalog import TargetCatalog


class TargetCatalogTests(unittest.TestCase):
    def test_process_catalog_declares_its_search_limit(self) -> None:
        catalog = TargetCatalog(
            ProcFs(Path("/missing")), MagicMock(), MagicMock(), MagicMock()
        )
        with patch("xray.targets.catalog.process_name", return_value="worker"):
            rows, limited = catalog._processes(
                list(range(1, LIMITS.catalog_processes + 2))
            )

        self.assertEqual(len(rows), LIMITS.catalog_processes)
        self.assertEqual(
            limited,
            [f"Process search is limited to {LIMITS.catalog_processes} entries"],
        )

    def test_catalog_collects_each_expensive_source_once(self) -> None:
        services = MagicMock()
        services.catalog.return_value = (
            [{"id": "demo.service", "scope": "user"}],
            [],
        )
        containers = MagicMock()
        containers.catalog.return_value = (
            [{"id": "demo", "runtime": "podman"}],
            [],
        )
        catalog = TargetCatalog(
            ProcFs(Path("/missing")), MagicMock(), services, containers
        )

        with (
            patch("xray.targets.catalog.same_user_pids", return_value=[41]),
            patch(
                "xray.targets.catalog.collect_descriptors",
                return_value=DescriptorInventory((), ()),
            ) as descriptors,
            patch(
                "xray.targets.catalog.list_windows",
                return_value=([{"address": "0xabc"}], ""),
            ) as windows,
            patch(
                "xray.targets.catalog.collect_pipewire",
                return_value=([{"pid": 41, "active": True}], ""),
            ) as pipewire,
            patch(
                "xray.targets.catalog.collect_gpu_clients",
                return_value=([{"pid": 41}], []),
            ) as gpu,
            patch.object(
                catalog,
                "_listening_ports",
                return_value=([{"localPort": 9000}], []),
            ) as ports,
            patch.object(
                catalog,
                "_processes",
                return_value=([{"pid": 41, "name": "worker"}], []),
            ) as processes,
        ):
            result = catalog.collect()

        expected_queries = {
            "windows": "window:0xabc",
            "processes": "pid:41",
            "devices": "pid:41",
            "gpu": "pid:41",
            "ports": ":9000",
            "services": "service:user:demo.service",
            "containers": "container:podman:demo",
        }
        for domain, query in expected_queries.items():
            with self.subTest(domain=domain):
                self.assertEqual(result[domain][0]["query"], query)
        for source in (descriptors, windows, pipewire, gpu, ports, processes):
            source.assert_called_once()
        services.catalog.assert_called_once()
        containers.catalog.assert_called_once()

    def test_independent_command_sources_are_collected_concurrently(self) -> None:
        windows_started = Event()
        devices_started = Event()

        def windows(_runner):
            windows_started.set()
            self.assertTrue(devices_started.wait(1), "device probe did not overlap")
            return [], ""

        def devices(_runner):
            devices_started.set()
            self.assertTrue(windows_started.wait(1), "window probe did not overlap")
            return [], ""

        services = MagicMock()
        services.catalog.return_value = ([], [])
        containers = MagicMock()
        containers.catalog.return_value = ([], [])
        catalog = TargetCatalog(
            ProcFs(Path("/missing")), MagicMock(), services, containers
        )
        with (
            patch("xray.targets.catalog.same_user_pids", return_value=[]),
            patch(
                "xray.targets.catalog.collect_descriptors",
                return_value=DescriptorInventory((), ()),
            ),
            patch("xray.targets.catalog.list_windows", side_effect=windows),
            patch("xray.targets.catalog.collect_pipewire", side_effect=devices),
            patch("xray.targets.catalog.collect_gpu_clients", return_value=([], [])),
            patch.object(catalog, "_listening_ports", return_value=([], [])),
        ):
            catalog.collect()

    def test_shared_descriptor_limit_is_counted_once(self) -> None:
        message = "Process 41 descriptors are permission-limited"
        services = MagicMock()
        services.catalog.return_value = ([], [])
        containers = MagicMock()
        containers.catalog.return_value = ([], [])
        catalog = TargetCatalog(
            ProcFs(Path("/missing")), MagicMock(), services, containers
        )

        with (
            patch("xray.targets.catalog.same_user_pids", return_value=[41]),
            patch(
                "xray.targets.catalog.collect_descriptors",
                return_value=DescriptorInventory((), (message,), (41,)),
            ),
            patch("xray.targets.catalog.list_windows", return_value=([], "")),
            patch("xray.targets.catalog.collect_pipewire", return_value=([], "")),
            patch(
                "xray.targets.catalog.collect_gpu_clients",
                return_value=([], [message]),
            ),
            patch.object(catalog, "_listening_ports", return_value=([], [message])),
            patch.object(catalog, "_processes", return_value=([], [])),
        ):
            result = catalog.collect()

        self.assertIn(
            "Open file details are unavailable for 1 same-user processes",
            result["limited"],
        )


if __name__ == "__main__":
    unittest.main()
