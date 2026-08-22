from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from xray.config import LIMITS
from xray.devices.gpu import collect_gpu_clients
from xray.devices.pipewire import collect_pipewire
from xray.network.sockets import owned_socket_rows
from xray.processes.collector import process_name
from xray.processes.identity import same_user_pids
from xray.runtime.containers import ContainerInspector
from xray.runtime.context import list_windows
from xray.runtime.systemd import SystemdInspector
from xray.system.commands import CommandRunner
from xray.system.descriptors import DescriptorInventory, collect_descriptors
from xray.system.procfs import ProcFs
from xray.targets.catalog_budget import constrain_catalog
from xray.targets.query import quick_targets


class TargetCatalog:
    """Builds the bounded resource catalog used by target search."""

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

    def collect(self) -> dict[str, object]:
        pids = same_user_pids(self.proc)
        with ThreadPoolExecutor(
            max_workers=7, thread_name_prefix="xray-catalog"
        ) as pool:
            descriptors_future = pool.submit(collect_descriptors, self.proc, pids)
            windows_future = pool.submit(list_windows, self.runner)
            devices_future = pool.submit(collect_pipewire, self.runner)
            services_future = pool.submit(self.systemd.catalog)
            containers_future = pool.submit(self.containers.catalog)
            processes_future = pool.submit(self._processes, pids)

            descriptors = descriptors_future.result()
            gpu_future = pool.submit(collect_gpu_clients, self.proc, pids, descriptors)
            ports_future = pool.submit(self._listening_ports, pids, descriptors)

            windows, window_error = windows_future.result()
            devices, device_error = devices_future.result()
            services, service_limited = services_future.result()
            containers, container_limited = containers_future.result()
            processes, process_limited = processes_future.result()
            gpu_clients, gpu_limited = gpu_future.result()
            ports, port_limited = ports_future.result()
        raw_limited = [
            message
            for message in (
                window_error,
                device_error,
                *descriptors.catalog_limitations(),
                *port_limited,
                *gpu_limited,
                *service_limited,
                *container_limited,
                *process_limited,
            )
            if message
        ]
        raw_limited = list(dict.fromkeys(raw_limited))
        return constrain_catalog(
            {
                "quickTargets": quick_targets(),
                "windows": windows,
                "processes": processes,
                "devices": [row for row in devices if row["active"]],
                "gpu": gpu_clients,
                "ports": ports,
                "services": services,
                "containers": containers,
                "limited": raw_limited,
            }
        )

    def _processes(self, pids: list[int]) -> tuple[list[dict[str, object]], list[str]]:
        rows = [{"pid": pid, "name": process_name(self.proc, pid)} for pid in pids]
        rows.sort(key=lambda row: (str(row["name"]).casefold(), int(row["pid"])))
        limited = (
            [f"Process search is limited to {LIMITS.catalog_processes} entries"]
            if len(rows) > LIMITS.catalog_processes
            else []
        )
        return rows[: LIMITS.catalog_processes], limited

    def _listening_ports(
        self, pids: list[int], descriptors: DescriptorInventory
    ) -> tuple[list[dict[str, object]], list[str]]:
        socket_data, limited = owned_socket_rows(self.proc, pids, descriptors)
        rows = [row for row in socket_data if row["listening"] and row["pids"]]
        rows.sort(key=lambda row: (int(row["localPort"]), str(row["protocol"])))
        if len(rows) > LIMITS.catalog_ports:
            limited.append(f"Port search is limited to {LIMITS.catalog_ports} entries")
        return rows[: LIMITS.catalog_ports], list(dict.fromkeys(limited))
