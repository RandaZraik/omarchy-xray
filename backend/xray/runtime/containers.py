from __future__ import annotations

import json
import os
import time

from xray.config import LIMITS, TIMING
from xray.evidence.redaction import redact_command
from xray.runtime.cache import RuntimeDetailsCache
from xray.system.commands import CommandRunner

SUPPORTED_CONTAINER_RUNTIMES = ("docker", "podman", "nerdctl")


def _local_unix_endpoint(value: object) -> bool:
    endpoint = str(value or "").strip()
    if endpoint.startswith("unix://"):
        endpoint = endpoint.removeprefix("unix://")
    return endpoint.startswith("/") and "\x00" not in endpoint


def _json_lines(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _labels(value: object) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    result: dict[str, str] = {}
    for pair in str(value or "").split(","):
        key, separator, item = pair.partition("=")
        if separator and key:
            result[key] = item
    return result


def parse_container_list(text: str, runtime: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        payload = None
    raw_rows = (
        [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, list)
        else _json_lines(text)
    )
    rows: list[dict[str, object]] = []
    for raw in raw_rows:
        identifier = str(raw.get("ID", raw.get("Id", raw.get("id", ""))))
        names = raw.get("Names", raw.get("Name", raw.get("names", "")))
        if isinstance(names, list):
            names = names[0] if names else ""
        name = str(names or "").lstrip("/")
        if not identifier or not name:
            continue
        labels = _labels(raw.get("Labels", raw.get("labels", {})))
        rows.append(
            {
                "id": identifier,
                "shortId": identifier[:12],
                "name": name,
                "image": str(raw.get("Image", raw.get("ImageName", ""))),
                "state": str(raw.get("State", raw.get("Status", ""))),
                "status": str(raw.get("Status", raw.get("RunningFor", ""))),
                "portsText": str(raw.get("Ports", "")),
                "runtime": runtime,
                "composeProject": labels.get("com.docker.compose.project", ""),
                "composeService": labels.get("com.docker.compose.service", ""),
            }
        )
    return rows


def _port_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, dict):
        return []
    rows: list[dict[str, object]] = []
    for container_endpoint, bindings in value.items():
        port, _, protocol = str(container_endpoint).partition("/")
        if not isinstance(bindings, list) or not bindings:
            continue
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            rows.append(
                {
                    "containerPort": port,
                    "protocol": protocol,
                    "hostAddress": str(binding.get("HostIp", "")),
                    "hostPort": str(binding.get("HostPort", "")),
                }
            )
    return rows


def parse_container_inspect(payload: object, runtime: str) -> dict[str, object]:
    raw = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(raw, dict):
        return {}
    config = raw.get("Config", {}) if isinstance(raw.get("Config"), dict) else {}
    state = raw.get("State", {}) if isinstance(raw.get("State"), dict) else {}
    host = raw.get("HostConfig", {}) if isinstance(raw.get("HostConfig"), dict) else {}
    network = (
        raw.get("NetworkSettings", {})
        if isinstance(raw.get("NetworkSettings"), dict)
        else {}
    )
    labels = _labels(config.get("Labels", raw.get("Labels", {})))
    restart = host.get("RestartPolicy", {})
    restart_name = (
        str(restart.get("Name", ""))
        if isinstance(restart, dict)
        else str(restart or "")
    )
    mounts: list[dict[str, object]] = []
    for mount in raw.get("Mounts", []) if isinstance(raw.get("Mounts"), list) else []:
        if not isinstance(mount, dict):
            continue
        mounts.append(
            {
                "type": str(mount.get("Type", "")),
                "source": str(mount.get("Source", "")),
                "destination": str(mount.get("Destination", "")),
                "readOnly": not bool(mount.get("RW", True)),
            }
        )
    networks = network.get("Networks", {})
    network_rows = (
        [
            {
                "name": str(name),
                "address": str(values.get("IPAddress", ""))
                if isinstance(values, dict)
                else "",
                "gateway": str(values.get("Gateway", ""))
                if isinstance(values, dict)
                else "",
            }
            for name, values in networks.items()
        ]
        if isinstance(networks, dict)
        else []
    )
    identifier = str(raw.get("Id", raw.get("ID", "")))
    try:
        pid = int(state.get("Pid", raw.get("Pid", 0)))
    except (TypeError, ValueError):
        pid = 0
    command = config.get("Cmd", [])
    entrypoint = config.get("Entrypoint", [])
    return {
        "id": identifier,
        "shortId": identifier[:12],
        "name": str(raw.get("Name", "")).lstrip("/"),
        "image": str(config.get("Image", raw.get("ImageName", ""))),
        "runtime": runtime,
        "pid": pid,
        "state": str(state.get("Status", raw.get("State", ""))),
        "running": bool(state.get("Running", pid > 0)),
        "created": str(raw.get("Created", "")),
        "command": redact_command(command),
        "entrypoint": redact_command(entrypoint),
        "restartPolicy": restart_name,
        "privileged": bool(host.get("Privileged", False)),
        "composeProject": labels.get("com.docker.compose.project", ""),
        "composeService": labels.get("com.docker.compose.service", ""),
        "composeWorkingDirectory": labels.get(
            "com.docker.compose.project.working_dir", ""
        ),
        "ports": _port_rows(network.get("Ports", {})),
        "mounts": mounts,
        "networks": network_rows,
    }


class ContainerInspector:
    def __init__(
        self, runner: CommandRunner, cache_seconds: float | None = None
    ) -> None:
        self.runner = runner
        self.cache_seconds = (
            TIMING.runtime_catalog_refresh_seconds
            if cache_seconds is None
            else cache_seconds
        )
        self._catalog: list[dict[str, object]] = []
        self._catalog_limited: list[str] = []
        self._catalog_at = 0.0
        self._details = RuntimeDetailsCache(
            self.cache_seconds, LIMITS.runtime_detail_cache_entries
        )
        self._locality: dict[str, tuple[float, bool, str]] = {}

    def invalidate(self) -> None:
        self._catalog_at = 0.0
        self._details.clear()
        self._locality.clear()

    def _runtime_locality(self, runtime: str) -> tuple[bool, str]:
        now = time.monotonic()
        cached = self._locality.get(runtime)
        if cached and now - cached[0] < self.cache_seconds:
            return cached[1], cached[2]
        local = False
        if runtime == "docker":
            endpoint = os.environ.get("DOCKER_HOST", "")
            if not endpoint:
                argv = ["docker", "context", "inspect"]
                if context := os.environ.get("DOCKER_CONTEXT"):
                    argv.append(context)
                result = self.runner.run(
                    argv, timeout_seconds=TIMING.slower_command_seconds
                )
                payload = result.json([])
                context_data = (
                    payload[0]
                    if isinstance(payload, list)
                    and payload
                    and isinstance(payload[0], dict)
                    else {}
                )
                endpoints = context_data.get("Endpoints", {})
                docker = (
                    endpoints.get("docker", {}) if isinstance(endpoints, dict) else {}
                )
                endpoint = docker.get("Host", "") if isinstance(docker, dict) else ""
            local = _local_unix_endpoint(endpoint)
        elif runtime == "podman":
            result = self.runner.run(
                ["podman", "info", "--format", "json"],
                timeout_seconds=TIMING.slower_command_seconds,
            )
            payload = result.json({})
            host = (
                payload.get("host", payload.get("Host", {}))
                if isinstance(payload, dict)
                else {}
            )
            local = (
                result.returncode == 0
                and isinstance(host, dict)
                and host.get("serviceIsRemote") is False
            )
        elif runtime == "nerdctl":
            endpoint = os.environ.get("CONTAINERD_ADDRESS", "")
            # nerdctl has no Docker-style SSH endpoint. Its documented default
            # is a local containerd Unix socket; an explicit address must prove
            # the same property.
            local = not endpoint or _local_unix_endpoint(endpoint)
        message = (
            ""
            if local
            else f"{runtime} uses a remote or unsupported endpoint; its local process could not be found"
        )
        self._locality[runtime] = (now, local, message)
        return local, message

    def catalog(self) -> tuple[list[dict[str, object]], list[str]]:
        now = time.monotonic()
        self._details.prune(now)
        if self._catalog_at and now - self._catalog_at < self.cache_seconds:
            return list(self._catalog), list(self._catalog_limited)
        rows: list[dict[str, object]] = []
        limited: list[str] = []
        for runtime in SUPPORTED_CONTAINER_RUNTIMES:
            if not self.runner.available(runtime):
                continue
            local, locality_error = self._runtime_locality(runtime)
            if not local:
                limited.append(locality_error)
                continue
            argv = [runtime, "ps", "--no-trunc"]
            argv.extend(
                ["--format", "json"]
                if runtime == "podman"
                else ["--format", "{{json .}}"]
            )
            result = self.runner.run(
                argv, timeout_seconds=TIMING.slower_command_seconds
            )
            if result.returncode == 0:
                rows.extend(parse_container_list(result.stdout, runtime))
            else:
                limited.append(f"{runtime} container catalog is unavailable")
        unique = {
            (str(row["runtime"]), str(row["id"])): row for row in rows if row.get("id")
        }
        self._catalog = sorted(
            unique.values(),
            key=lambda row: (str(row["runtime"]), str(row["name"]).casefold()),
        )[: LIMITS.catalog_containers]
        if len(unique) > LIMITS.catalog_containers:
            limited.append(
                f"Container catalog is limited to {LIMITS.catalog_containers} running containers"
            )
        self._catalog_limited = list(dict.fromkeys(limited))
        self._catalog_at = now
        return list(self._catalog), list(self._catalog_limited)

    def details(self, identifier: str, runtime: str = "") -> dict[str, object]:
        runtimes = (
            [runtime]
            if runtime in SUPPORTED_CONTAINER_RUNTIMES
            else list(SUPPORTED_CONTAINER_RUNTIMES)
        )
        now = time.monotonic()
        self._details.prune(now)
        for candidate in runtimes:
            if not self.runner.available(candidate):
                continue
            local, _ = self._runtime_locality(candidate)
            if not local:
                continue
            key = (candidate, identifier)
            cached, value = self._details.get(key, now)
            if cached:
                if value:
                    return value
                continue
            result = self.runner.run(
                [candidate, "inspect", "--", identifier],
                timeout_seconds=TIMING.slower_command_seconds,
            )
            details = (
                parse_container_inspect(result.json([]), candidate)
                if result.returncode == 0
                else {}
            )
            self._details.put(key, details, now)
            if details:
                return dict(details)
        return {}

    def details_with_evidence(
        self, identifier: str, runtime: str = ""
    ) -> tuple[dict[str, object], list[str]]:
        if runtime in SUPPORTED_CONTAINER_RUNTIMES and self.runner.available(runtime):
            local, locality_error = self._runtime_locality(runtime)
            if not local:
                return {}, [locality_error]
        details = self.details(identifier, runtime)
        if details:
            return details, []
        if any(self.runner.available(value) for value in SUPPORTED_CONTAINER_RUNTIMES):
            return {}, [f"Container details for {identifier} are unavailable"]
        return {}, []

    def for_cgroup_with_evidence(
        self, container_id: str
    ) -> tuple[dict[str, object], list[str]]:
        if not container_id:
            return {}, []
        direct, direct_limited = self.details_with_evidence(container_id)
        if direct:
            return direct, []
        rows, catalog_limited = self.catalog()
        row = next(
            (
                item
                for item in rows
                if str(item.get("id", "")).startswith(container_id)
                or container_id.startswith(str(item.get("shortId", "")))
            ),
            None,
        )
        if row:
            details, detail_limited = self.details_with_evidence(
                str(row["id"]), str(row["runtime"])
            )
            return details, list(dict.fromkeys([*catalog_limited, *detail_limited]))
        return {}, list(dict.fromkeys([*catalog_limited, *direct_limited]))
