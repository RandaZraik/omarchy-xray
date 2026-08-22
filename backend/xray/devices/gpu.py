from __future__ import annotations

from dataclasses import dataclass, field
import re
import time

from xray.system.procfs import ProcFs
from xray.system.descriptors import (
    DescriptorInventory,
    collect_descriptors,
    read_stable_fdinfo,
)


_ENGINE = re.compile(r"^drm-engine-([^:]+):\s*(\d+)\s*ns$", re.MULTILINE)
_CAPACITY = re.compile(r"^drm-engine-capacity-([^:]+):\s*(\d+)$", re.MULTILINE)
_MEMORY = re.compile(
    r"^drm-(memory|resident|total)-([^:]+):\s*(\d+)\s*([KMGT]?i?B)?$",
    re.MULTILINE | re.IGNORECASE,
)


def _bytes(value: str, unit: str) -> int:
    factors = {
        "": 1,
        "b": 1,
        "kb": 1000,
        "kib": 1024,
        "mb": 1_000_000,
        "mib": 1_048_576,
        "gb": 1_000_000_000,
        "gib": 1_073_741_824,
        "tb": 1_000_000_000_000,
        "tib": 1_099_511_627_776,
    }
    return int(value) * factors.get(unit.lower(), 1)


def parse_drm_fdinfo(text: str) -> dict[str, object] | None:
    match = re.search(r"^drm-client-id:\s*(\S+)$", text, re.MULTILINE)
    if not match:
        return None
    engines = {name: int(value) for name, value in _ENGINE.findall(text)}
    capacity = {name: max(1, int(value)) for name, value in _CAPACITY.findall(text)}
    memory_groups: dict[str, dict[str, int]] = {
        "memory": {},
        "resident": {},
        "total": {},
    }
    for category, name, value, unit in _MEMORY.findall(text):
        memory_groups[category.lower()][name] = _bytes(value, unit or "")
    memory = (
        memory_groups["resident"] or memory_groups["total"] or memory_groups["memory"]
    )
    return {
        "clientId": match.group(1),
        "engines": engines,
        "capacity": capacity,
        "memory": memory,
        "memoryKind": (
            "resident"
            if memory_groups["resident"]
            else "total"
            if memory_groups["total"]
            else "legacy"
        ),
    }


def collect_gpu_clients(
    proc: ProcFs,
    pids: list[int],
    inventory: DescriptorInventory | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    limited: list[str] = []
    seen: set[tuple[int, str, str]] = set()
    descriptors = inventory or collect_descriptors(proc, pids)
    limited.extend(descriptors.limited)
    for record in descriptors.records:
        if not record.target.startswith("/dev/dri/"):
            continue
        info = read_stable_fdinfo(proc, record, limit=131_072)
        if not info.available:
            limited.append(
                f"GPU fdinfo for process {record.pid} is unavailable: {info.error}"
            )
            continue
        parsed = parse_drm_fdinfo(info.value)
        if not parsed:
            limited.append(
                f"GPU fdinfo for process {record.pid} has no DRM client identity"
            )
            continue
        key = (record.pid, record.target, str(parsed["clientId"]))
        if key in seen:
            continue
        seen.add(key)
        rows.append({"pid": record.pid, "device": record.target, **parsed})
    return rows, list(dict.fromkeys(limited))


@dataclass
class GpuSampler:
    previous_at: float = 0.0
    previous_engines: dict[str, dict[str, int]] = field(default_factory=dict)

    def sample(
        self, clients: list[dict[str, object]], now: float | None = None
    ) -> float | None:
        sampled_at = now if now is not None else time.monotonic()
        elapsed_ns = (
            max(1.0, (sampled_at - self.previous_at) * 1_000_000_000)
            if self.previous_at
            else 0.0
        )
        current: dict[str, dict[str, int]] = {}
        total_delta = 0
        missing_baseline = False
        device_capacity: dict[tuple[str, str], int] = {}
        for client in clients:
            key = f"{client['pid']}:{client['device']}:{client['clientId']}"
            engines = {
                str(name): int(value)
                for name, value in dict(client.get("engines", {})).items()
            }
            current[key] = engines
            previous = self.previous_engines.get(key)
            if self.previous_at and previous is None:
                missing_baseline = True
            capacities = {
                str(name): max(1, int(value))
                for name, value in dict(client.get("capacity", {})).items()
            }
            deltas = (
                {
                    name: max(0, value - previous.get(name, value))
                    for name, value in engines.items()
                }
                if previous is not None
                else {}
            )
            utilization: float | None = None
            if elapsed_ns > 0 and previous is not None:
                denominator = elapsed_ns * sum(
                    capacities.get(name, 1) for name in engines
                )
                if denominator:
                    utilization = min(100.0, sum(deltas.values()) / denominator * 100)
            client["utilizationPercent"] = (
                round(utilization, 1) if utilization is not None else None
            )
            client["memoryBytes"] = sum(
                int(value) for value in dict(client.get("memory", {})).values()
            )
            total_delta += sum(deltas.values())
            for name in engines:
                capacity_key = (str(client["device"]), name)
                device_capacity[capacity_key] = max(
                    device_capacity.get(capacity_key, 0), capacities.get(name, 1)
                )
        self.previous_at = sampled_at
        self.previous_engines = current
        if elapsed_ns <= 0 or not device_capacity or missing_baseline:
            return None
        denominator = elapsed_ns * sum(device_capacity.values())
        return round(min(100.0, total_delta / denominator * 100), 1)
