from __future__ import annotations

import json
import time

from xray.config import LIMITS, TIMING
from xray.runtime.cache import RuntimeDetailsCache
from xray.system.commands import CommandRunner
from xray.system.procfs import (
    ProcFs,
    cgroup_paths,
    parse_key_values,
    systemd_scope_from_cgroup,
    unit_from_cgroup,
)

_UNIT_PROPERTIES = (
    "Id,Description,MainPID,ControlGroup,LoadState,ActiveState,SubState,"
    "FragmentPath,TriggeredBy,Triggers,UnitFileState"
)


def parse_show(text: str, scope: str) -> dict[str, object]:
    values = parse_key_values(text, "=")
    identifier = values.get("Id", "")
    if not identifier:
        return {}
    try:
        main_pid = int(values.get("MainPID", "0"))
    except ValueError:
        main_pid = 0
    return {
        "id": identifier,
        "description": values.get("Description", "") or identifier,
        "scope": scope,
        "mainPid": main_pid,
        "controlGroup": values.get("ControlGroup", ""),
        "loadState": values.get("LoadState", ""),
        "activeState": values.get("ActiveState", ""),
        "subState": values.get("SubState", ""),
        "fragmentPath": values.get("FragmentPath", ""),
        "unitFileState": values.get("UnitFileState", ""),
        "triggeredBy": values.get("TriggeredBy", "").split(),
        "triggers": values.get("Triggers", "").split(),
    }


def parse_unit_list(text: str, scope: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        payload = None
    rows: list[dict[str, object]] = []
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict) or not item.get("unit"):
                continue
            rows.append(
                {
                    "id": str(item["unit"]),
                    "description": str(item.get("description", "") or item["unit"]),
                    "scope": scope,
                    "loadState": str(item.get("load", "")),
                    "activeState": str(item.get("active", "")),
                    "subState": str(item.get("sub", "")),
                }
            )
        return rows

    for line in text.splitlines():
        fields = line.split(maxsplit=4)
        if len(fields) < 4 or not fields[0].endswith((".service", ".scope")):
            continue
        rows.append(
            {
                "id": fields[0],
                "loadState": fields[1],
                "activeState": fields[2],
                "subState": fields[3],
                "description": fields[4] if len(fields) > 4 else fields[0],
                "scope": scope,
            }
        )
    return rows


class SystemdInspector:
    def __init__(
        self, proc: ProcFs, runner: CommandRunner, cache_seconds: float | None = None
    ) -> None:
        self.proc = proc
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

    def invalidate(self) -> None:
        self._catalog_at = 0.0
        self._details.clear()

    def catalog(self) -> tuple[list[dict[str, object]], list[str]]:
        now = time.monotonic()
        self._details.prune(now)
        if self._catalog_at and now - self._catalog_at < self.cache_seconds:
            return list(self._catalog), list(self._catalog_limited)
        rows: list[dict[str, object]] = []
        limited: list[str] = []
        for scope in ("user", "system"):
            argv = ["systemctl"]
            if scope == "user":
                argv.append("--user")
            argv.extend(
                [
                    "list-units",
                    "--type=service",
                    "--type=scope",
                    "--state=running",
                    "--no-pager",
                    "--output=json",
                ]
            )
            result = self.runner.run(argv)
            if result.returncode == 0:
                rows.extend(parse_unit_list(result.stdout, scope))
            elif not result.unavailable:
                limited.append(f"{scope.title()} service catalog is unavailable")
        unique = {
            (str(row["scope"]), str(row["id"])): row for row in rows if row.get("id")
        }
        self._catalog = sorted(
            unique.values(),
            key=lambda row: (str(row["scope"]), str(row["id"]).casefold()),
        )[: LIMITS.catalog_services]
        if len(unique) > LIMITS.catalog_services:
            limited.append(
                f"Service catalog is limited to {LIMITS.catalog_services} running units"
            )
        self._catalog_limited = list(dict.fromkeys(limited))
        self._catalog_at = now
        return list(self._catalog), list(self._catalog_limited)

    def details(self, unit: str, preferred_scope: str = "") -> dict[str, object]:
        scopes = (
            [preferred_scope]
            if preferred_scope in {"user", "system"}
            else ["user", "system"]
        )
        now = time.monotonic()
        for scope in scopes:
            key = (scope, unit)
            cached, value = self._details.get(key, now)
            if cached:
                if value:
                    return value
                continue
            argv = ["systemctl"]
            if scope == "user":
                argv.append("--user")
            argv.extend(
                ["show", "--no-pager", f"--property={_UNIT_PROPERTIES}", "--", unit]
            )
            result = self.runner.run(argv)
            details = parse_show(result.stdout, scope) if result.returncode == 0 else {}
            if details.get("loadState") == "not-found":
                details = {}
            self._details.put(key, details, now)
            if details:
                return dict(details)
        return {}

    def details_with_evidence(
        self, unit: str, preferred_scope: str = ""
    ) -> tuple[dict[str, object], list[str]]:
        details = self.details(unit, preferred_scope)
        if details:
            return details, []
        return {}, [f"Systemd details for {unit} are unavailable"]

    def pids(self, unit: str, preferred_scope: str = "") -> list[int]:
        details = self.details(unit, preferred_scope)
        main_pid = int(details.get("mainPid", 0)) if details else 0
        control_group = str(details.get("controlGroup", "")).rstrip("/")
        matches: set[int] = (
            {main_pid} if main_pid > 0 and self.proc.path(main_pid).exists() else set()
        )
        if not control_group:
            return sorted(matches)
        for pid in self.proc.pids():
            result = self.proc.read(pid, "cgroup", limit=131_072)
            if result.available and any(
                path == control_group or path.startswith(control_group + "/")
                for path in cgroup_paths(result.value)
            ):
                matches.add(pid)
        return (
            [main_pid, *sorted(matches - {main_pid})]
            if main_pid in matches
            else sorted(matches)
        )

    def for_process_with_evidence(
        self, pid: int
    ) -> tuple[dict[str, object], list[str]]:
        result = self.proc.read(pid, "cgroup", limit=131_072)
        if not result.available:
            return {}, [f"Systemd details for process {pid} are unavailable"]
        unit = unit_from_cgroup(result.value)
        scope = systemd_scope_from_cgroup(result.value)
        return self.details_with_evidence(unit, scope) if unit else ({}, [])
