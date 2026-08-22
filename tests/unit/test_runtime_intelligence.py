from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from xray.runtime.causality import build_cause_chain, process_ancestry
from xray.runtime.containers import (
    ContainerInspector,
    parse_container_inspect,
    parse_container_list,
)
from xray.runtime.cache import RuntimeDetailsCache
from xray.runtime.systemd import (
    SystemdInspector,
    parse_show,
    parse_unit_list,
    unit_from_cgroup,
)
from xray.system.commands import CommandResult
from xray.system.procfs import ProcFs
from support.procfs import write_process as write_proc_process


def write_process(
    root: Path, pid: int, name: str, ppid: int, start: int, cgroup: str = ""
) -> None:
    write_proc_process(
        root,
        pid,
        name,
        ppid,
        start=start,
        command=name.encode() + b"\0--safe\0",
        cgroup=cgroup,
    )


class FakeRunner:
    def __init__(
        self,
        replies: dict[tuple[str, ...], CommandResult],
        available: set[str] | None = None,
    ) -> None:
        self.replies = replies
        self.available_commands = available or set()
        self.calls: list[tuple[str, ...]] = []

    def available(self, executable: str) -> bool:
        return executable in self.available_commands

    def run(self, argv, **_kwargs) -> CommandResult:
        key = tuple(argv)
        self.calls.append(key)
        return self.replies.get(key, CommandResult(key, 1, "", "missing fixture"))


class RuntimeCacheTests(unittest.TestCase):
    def test_detail_cache_is_ttl_bounded_and_lru(self) -> None:
        cache = RuntimeDetailsCache(ttl_seconds=10, max_entries=2)
        cache.put("first", {"id": 1}, now=0)
        cache.put("second", {"id": 2}, now=1)
        self.assertEqual(cache.get("first", now=2), (True, {"id": 1}))

        cache.put("third", {"id": 3}, now=3)

        self.assertEqual(cache.get("second", now=3), (False, {}))
        self.assertEqual(cache.get("first", now=3), (True, {"id": 1}))
        cache.prune(now=13)
        self.assertEqual(len(cache), 0)


class RuntimeIntelligenceTests(unittest.TestCase):
    def test_systemd_parsers_keep_scope_trigger_and_exact_unit(self) -> None:
        units = parse_unit_list(
            json.dumps(
                [
                    {
                        "unit": "demo.service",
                        "load": "loaded",
                        "active": "active",
                        "sub": "running",
                        "description": "Demo",
                    }
                ]
            ),
            "user",
        )
        self.assertEqual(units[0]["id"], "demo.service")
        self.assertEqual(units[0]["scope"], "user")
        details = parse_show(
            "Id=demo.service\nDescription=Demo worker\nMainPID=41\nControlGroup=/user.slice/demo.service\n"
            "LoadState=loaded\nActiveState=active\nSubState=running\nFragmentPath=/home/u/.config/systemd/user/demo.service\n"
            "TriggeredBy=demo.timer demo.socket\nTriggers=\nUnitFileState=enabled\n",
            "user",
        )
        self.assertEqual(details["mainPid"], 41)
        self.assertEqual(details["triggeredBy"], ["demo.timer", "demo.socket"])
        self.assertEqual(
            unit_from_cgroup("0::/user.slice/app.slice/demo.service\n"), "demo.service"
        )

    def test_systemd_inspector_catalog_details_and_pid_membership_are_cached(
        self,
    ) -> None:
        user_list = (
            "systemctl",
            "--user",
            "list-units",
            "--type=service",
            "--type=scope",
            "--state=running",
            "--no-pager",
            "--output=json",
        )
        system_list = (
            "systemctl",
            "list-units",
            "--type=service",
            "--type=scope",
            "--state=running",
            "--no-pager",
            "--output=json",
        )
        show = (
            "systemctl",
            "--user",
            "show",
            "--no-pager",
            "--property=Id,Description,MainPID,ControlGroup,LoadState,ActiveState,SubState,FragmentPath,TriggeredBy,Triggers,UnitFileState",
            "--",
            "demo.service",
        )
        replies = {
            user_list: CommandResult(
                user_list,
                0,
                '[{"unit":"demo.service","load":"loaded","active":"active","sub":"running","description":"Demo"}]',
                "",
            ),
            system_list: CommandResult(system_list, 0, "[]", ""),
            show: CommandResult(
                show,
                0,
                "Id=demo.service\nDescription=Demo\nMainPID=41\n"
                "ControlGroup=/user.slice/user-1000.slice/user@1000.service/app.slice/demo.service\n"
                "LoadState=loaded\nActiveState=active\nSubState=running\n",
                "",
            ),
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            user_group = (
                "/user.slice/user-1000.slice/user@1000.service/app.slice/demo.service"
            )
            write_process(root, 41, "demo", 1, 100, f"0::{user_group}\n")
            write_process(root, 42, "worker", 41, 101, f"0::{user_group}\n")
            write_process(
                root, 43, "system-demo", 1, 102, "0::/system.slice/demo.service\n"
            )
            runner = FakeRunner(replies)
            inspector = SystemdInspector(ProcFs(root), runner, cache_seconds=60)
            self.assertEqual(inspector.catalog()[0][0]["id"], "demo.service")
            self.assertEqual(inspector.pids("demo.service", "user"), [41, 42])
            details, limited = inspector.for_process_with_evidence(42)
            self.assertEqual(limited, [])
            self.assertEqual(details["mainPid"], 41)
            inspector.catalog()
        self.assertEqual(runner.calls.count(user_list), 1)
        self.assertEqual(runner.calls.count(show), 1)

    def test_explicit_systemd_scope_never_falls_through_to_another_manager(
        self,
    ) -> None:
        property_arg = (
            "--property=Id,Description,MainPID,ControlGroup,LoadState,ActiveState,"
            "SubState,FragmentPath,TriggeredBy,Triggers,UnitFileState"
        )
        system_show = (
            "systemctl",
            "show",
            "--no-pager",
            property_arg,
            "--",
            "demo.service",
        )
        user_show = (
            "systemctl",
            "--user",
            "show",
            "--no-pager",
            property_arg,
            "--",
            "demo.service",
        )
        runner = FakeRunner(
            {
                system_show: CommandResult(system_show, 1, "", "not found"),
                user_show: CommandResult(
                    user_show,
                    0,
                    "Id=demo.service\nLoadState=loaded\nMainPID=41\n",
                    "",
                ),
            }
        )

        details = SystemdInspector(ProcFs(Path("/missing")), runner).details(
            "demo.service", "system"
        )

        self.assertEqual(details, {})
        self.assertEqual(runner.calls, [system_show])

    def test_failed_runtime_detail_commands_remain_visible_as_limitations(self) -> None:
        property_arg = (
            "--property=Id,Description,MainPID,ControlGroup,LoadState,ActiveState,"
            "SubState,FragmentPath,TriggeredBy,Triggers,UnitFileState"
        )
        show = (
            "systemctl",
            "--user",
            "show",
            "--no-pager",
            property_arg,
            "--",
            "demo.service",
        )
        systemd = SystemdInspector(
            ProcFs(Path("/missing")),
            FakeRunner({show: CommandResult(show, 1, "", "failed")}),
        )
        details, limited = systemd.details_with_evidence("demo.service", "user")
        self.assertEqual(details, {})
        self.assertIn("demo.service", limited[0])

        context = ("docker", "context", "inspect")
        runner = FakeRunner(
            {
                context: CommandResult(
                    context,
                    0,
                    '[{"Endpoints":{"docker":{"Host":"unix:///var/run/docker.sock"}}}]',
                    "",
                )
            },
            {"docker"},
        )
        container, limited = ContainerInspector(runner).details_with_evidence(
            "abcdef123456", "docker"
        )
        self.assertEqual(container, {})
        self.assertIn("abcdef123456", limited[0])

    def test_container_parsers_keep_runtime_ownership_without_environment_values(
        self,
    ) -> None:
        listed = parse_container_list(
            '{"ID":"abcdef1234567890","Names":"db","Image":"postgres:16","State":"running",'
            '"Labels":"com.docker.compose.project=demo,com.docker.compose.service=database"}\n',
            "docker",
        )
        self.assertEqual(listed[0]["composeProject"], "demo")
        payload = [
            {
                "Id": "abcdef1234567890",
                "Name": "/db",
                "Config": {
                    "Image": "postgres:16",
                    "Cmd": ["postgres", "--password", "command-secret"],
                    "Entrypoint": ["launcher", "--token=entry-secret"],
                    "Env": ["PASSWORD=secret"],
                    "Labels": {"com.docker.compose.project": "demo"},
                },
                "State": {"Pid": 73, "Running": True, "Status": "running"},
                "HostConfig": {
                    "Privileged": False,
                    "RestartPolicy": {"Name": "unless-stopped"},
                },
                "NetworkSettings": {
                    "Ports": {
                        "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15432"}],
                        "Networks": {"demo": {"IPAddress": "10.0.0.2"}},
                    }
                },
                "Mounts": [
                    {
                        "Type": "volume",
                        "Source": "/data/db",
                        "Destination": "/var/lib/postgresql/data",
                        "RW": False,
                    }
                ],
            }
        ]
        details = parse_container_inspect(payload, "docker")
        self.assertEqual(details["pid"], 73)
        self.assertEqual(details["ports"][0]["hostPort"], "15432")
        self.assertTrue(details["mounts"][0]["readOnly"])
        self.assertNotIn("Env", details)
        self.assertNotIn("secret", repr(details))
        self.assertEqual(details["command"], ["postgres", "--password", "<redacted>"])
        self.assertEqual(details["entrypoint"], ["launcher", "--token=<redacted>"])

        payload[0]["Config"]["Entrypoint"] = None
        self.assertEqual(parse_container_inspect(payload, "docker")["entrypoint"], [])

    def test_exposed_but_unbound_container_ports_are_not_called_published(self) -> None:
        details = parse_container_inspect(
            {
                "Id": "abcdef",
                "Config": {},
                "State": {},
                "NetworkSettings": {"Ports": {"80/tcp": None}},
            },
            "docker",
        )
        self.assertEqual(details["ports"], [])

    def test_container_inspector_catalog_and_details_keep_the_same_runtime(
        self,
    ) -> None:
        listing = ("docker", "ps", "--no-trunc", "--format", "{{json .}}")
        inspect = ("docker", "inspect", "--", "abcdef1234567890")
        context = ("docker", "context", "inspect")
        replies = {
            context: CommandResult(
                context,
                0,
                '[{"Endpoints":{"docker":{"Host":"unix:///var/run/docker.sock"}}}]',
                "",
            ),
            listing: CommandResult(
                listing,
                0,
                '{"ID":"abcdef1234567890","Names":"db","Image":"postgres:16","State":"running"}\n',
                "",
            ),
            inspect: CommandResult(
                inspect,
                0,
                json.dumps(
                    [
                        {
                            "Id": "abcdef1234567890",
                            "Name": "/db",
                            "Config": {"Image": "postgres:16"},
                            "State": {"Pid": 73, "Running": True},
                        }
                    ]
                ),
                "",
            ),
        }
        runner = FakeRunner(replies, {"docker"})
        inspector = ContainerInspector(runner, cache_seconds=60)
        listed = inspector.catalog()[0][0]
        resolved = inspector.details(str(listed["id"]), str(listed["runtime"]))
        self.assertEqual(resolved["runtime"], "docker")
        self.assertEqual(resolved["pid"], 73)
        details, limited = inspector.for_cgroup_with_evidence("abcdef123456")
        self.assertEqual(limited, [])
        self.assertEqual(details["name"], "db")
        self.assertEqual(runner.calls.count(listing), 1)
        self.assertEqual(runner.calls.count(inspect), 1)

    def test_remote_docker_context_is_rejected_before_runtime_queries(self) -> None:
        context = ("docker", "context", "inspect")
        listing = ("docker", "ps", "--no-trunc", "--format", "{{json .}}")
        runner = FakeRunner(
            {
                context: CommandResult(
                    context,
                    0,
                    '[{"Endpoints":{"docker":{"Host":"ssh://host/run/docker.sock"}}}]',
                    "",
                )
            },
            {"docker"},
        )

        rows, limited = ContainerInspector(runner).catalog()

        self.assertEqual(rows, [])
        self.assertIn("remote or unsupported endpoint", limited[0])
        self.assertNotIn(listing, runner.calls)

    def test_cause_chain_is_ordered_proof_and_replaces_duplicate_semantic_processes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 1, "systemd", 0, 1)
            write_process(root, 40, "demo", 1, 2)
            write_process(root, 41, "worker", 40, 3)
            (root / "41/cmdline").write_bytes(b"worker\0--token\0secret\0")
            proc = ProcFs(root)
            self.assertEqual(
                [row["pid"] for row in process_ancestry(proc, 41)], [1, 40, 41]
            )
            cause = build_cause_chain(
                proc,
                41,
                {
                    "id": "demo.service",
                    "description": "Demo",
                    "scope": "user",
                    "mainPid": 40,
                    "triggeredBy": ["demo.timer"],
                    "fragmentPath": "/unit/demo.service",
                },
                {},
            )
        self.assertEqual(cause["status"], "Confirmed")
        self.assertEqual(
            [row["kind"] for row in cause["nodes"]],
            ["supervisor", "service", "process"],
        )
        self.assertEqual(cause["summary"], "Started by demo.service")
        self.assertNotIn("Activated by", cause["summary"])
        self.assertEqual(
            sum(row["title"] == "demo.service" for row in cause["nodes"]), 1
        )
        self.assertTrue(all(row.get("proof") for row in cause["nodes"]))
        self.assertNotIn("secret", repr(cause))

    def test_transient_scope_without_main_pid_stays_before_the_owned_process(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 1, "systemd", 0, 1)
            write_process(root, 41, "editor", 1, 3)
            cause = build_cause_chain(
                ProcFs(root),
                41,
                {
                    "id": "app-editor.scope",
                    "description": "Editor",
                    "scope": "user",
                    "mainPid": 0,
                    "fragmentPath": "/run/user/1000/app-editor.scope",
                },
                {},
            )
        self.assertEqual(
            [row["title"] for row in cause["nodes"]],
            ["systemd", "app-editor.scope", "editor"],
        )

    def test_live_parent_chain_does_not_claim_original_launch_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(root, 20, "ghostty", 1, 1)
            write_process(root, 21, "worker", 20, 2)
            cause = build_cause_chain(ProcFs(root), 21, {}, {})

        self.assertEqual(cause["status"], "Partial")
        self.assertIn("Current parent chain", cause["summary"])
        self.assertIn("original launcher is no longer available", cause["summary"])


if __name__ == "__main__":
    unittest.main()
