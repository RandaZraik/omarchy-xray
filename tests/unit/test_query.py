from pathlib import Path
import unittest

from xray.config import LIMITS
from xray.targets.query import (
    TargetSpec,
    canonical_query,
    parse_query,
    quick_targets,
    rank_containers,
    rank_services,
)


class QueryTests(unittest.TestCase):
    def test_canonical_queries_reopen_every_explicit_target(self) -> None:
        expected = {
            TargetSpec("process", "42", "Process"): "pid:42",
            TargetSpec("port", "9000", "Port"): ":9000",
            TargetSpec("window", "0xabc", "Window"): "window:0xabc",
            TargetSpec(
                "service", "user:demo.service", "Service"
            ): "service:user:demo.service",
            TargetSpec(
                "container", "podman:demo", "Container"
            ): "container:podman:demo",
            TargetSpec("device", "camera", "Camera"): "camera",
            TargetSpec("file", "/tmp/demo", "File"): "/tmp/demo",
        }
        for spec, query in expected.items():
            with self.subTest(spec=spec):
                self.assertEqual(canonical_query(spec), query)

    def test_picked_point_canonicalizes_to_the_resolved_window(self) -> None:
        picked = TargetSpec("window-point", "120,240", "Picked window")

        self.assertEqual(canonical_query(picked, "0xabc"), "window:0xabc")
        self.assertEqual(canonical_query(picked), "")

    def test_quick_targets_share_the_parser_contract(self) -> None:
        targets = quick_targets()
        self.assertEqual(
            [target["label"] for target in targets],
            ["Microphone", "Camera", "Audio", "GPU"],
        )
        for target in targets:
            with self.subTest(target=target):
                parsed = parse_query(target["query"])
                self.assertEqual(parsed.kind, "device")
                self.assertEqual(parsed.value, target["query"])

    def test_runtime_targets_are_ranked_by_query_policy(self) -> None:
        services = [
            {"id": "other.service", "description": "Demo helper", "scope": "system"},
            {"id": "demo.service", "description": "Demo", "scope": "user"},
        ]
        containers = [
            {"id": "abc", "name": "database", "image": "postgres:16"},
            {"id": "def", "name": "postgres", "image": "demo:latest"},
        ]

        self.assertEqual(rank_services(services, "demo", "user"), [services[1]])
        self.assertEqual(rank_containers(containers, "postgres")[0], containers[1])

    def test_empty_query_opens_catalog(self) -> None:
        self.assertEqual(parse_query("").kind, "catalog")

    def test_query_text_is_bounded_before_catalog_matching(self) -> None:
        with self.assertRaisesRegex(ValueError, "size limit"):
            parse_query("x" * (LIMITS.query_bytes + 1))

    def test_process_variants(self) -> None:
        self.assertEqual(parse_query("1234").value, "1234")
        self.assertEqual(parse_query("pid: 42").kind, "process")

    def test_exact_window_addresses_are_explicit(self) -> None:
        self.assertEqual(parse_query("window:0xABC123").value, "0xabc123")
        self.assertEqual(parse_query("window:not-an-address").kind, "application")

    def test_port_variants_and_bounds(self) -> None:
        self.assertEqual(parse_query(":5173").value, "5173")
        self.assertEqual(parse_query("port 443").kind, "port")
        self.assertEqual(parse_query(":99999").kind, "application")

    def test_resources_are_explicit_not_questions(self) -> None:
        self.assertEqual(parse_query("mic").value, "microphone")
        self.assertEqual(parse_query("GPU").value, "gpu")
        self.assertEqual(parse_query("what uses my mic?").kind, "application")

    def test_services_and_containers_are_explicit(self) -> None:
        service = parse_query("service: demo.service")
        self.assertEqual((service.kind, service.value), ("service", "demo.service"))
        scoped = parse_query("service:user:demo.service")
        self.assertEqual(
            (scoped.kind, scoped.value, scoped.label),
            ("service", "user:demo.service", "User service demo.service"),
        )
        unit = parse_query("unit:demo.socket")
        self.assertEqual((unit.kind, unit.value), ("application", "unit:demo.socket"))
        container = parse_query("container: postgres")
        self.assertEqual((container.kind, container.value), ("container", "postgres"))
        qualified = parse_query("container:podman:postgres")
        self.assertEqual(
            (qualified.kind, qualified.value, qualified.label),
            ("container", "podman:postgres", "Podman container postgres"),
        )
        self.assertEqual(parse_query("service:user:").kind, "application")
        self.assertEqual(parse_query("container:docker:").kind, "application")

    def test_file_paths_expand_home(self) -> None:
        target = parse_query("~/notes.txt", Path("/users/example"))
        self.assertEqual(target.kind, "file")
        self.assertEqual(target.value, "/users/example/notes.txt")


if __name__ == "__main__":
    unittest.main()
