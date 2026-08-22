import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
from unittest.mock import MagicMock

from xray import SCHEMA_VERSION
from xray.capsules.archive import (
    CapsuleError,
    compare_capsule,
    default_export_directory,
    export_capsule,
    load_capsule,
    validate_snapshot,
)
from xray.capsules.service import CapsuleService
from xray.config import CAPSULE_SCHEMA


def capsule_snapshot(**overrides) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "schema": SCHEMA_VERSION,
        "target": {},
        "context": {},
        "metrics": {},
        "processes": [],
        "connections": [],
        "files": [],
        "locks": [],
        "devices": {
            "pipewire": [],
            "gpu": [],
            "inhibitors": [],
            "availability": {},
        },
        "security": {},
        "logs": [],
        "coverage": {"available": [], "limited": []},
        "actions": [],
        "explanations": [],
        "changes": {},
        "timeline": [],
        "settings": {},
    }
    snapshot.update(overrides)
    return snapshot


class CapsuleTests(unittest.TestCase):
    def test_service_exports_opens_compares_and_reports_sanitized_evidence(
        self,
    ) -> None:
        service = CapsuleService()
        snapshot = capsule_snapshot(
            target={"label": "Editor", "rootPid": 42},
            metrics={
                "processCount": 2,
                "cpuPercent": 4.5,
                "memoryBytes": 1024,
                "gpuPercent": None,
            },
            explanations=[
                {
                    "title": "File is open",
                    "why": str(Path.home() / "private.txt"),
                }
            ],
        )
        with TemporaryDirectory() as directory:
            exported = service.export(snapshot, directory)
            opened = service.open(exported["path"])
            comparison = service.compare(snapshot, exported["path"])
        report = service.report(snapshot)["text"]

        self.assertEqual(opened["snapshot"]["target"]["rootPid"], 42)
        self.assertEqual(comparison["domains"]["processes"], {"added": 0, "removed": 0})
        self.assertIn("CPU: 4.5%", report)
        self.assertIn("GPU: unavailable", report)
        self.assertNotIn(str(Path.home()), report)

    def test_default_export_directory_honors_xdg_user_dirs_and_falls_back(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch.dict("os.environ", {}, clear=True),
        ):
            home = Path(directory)
            downloads = home / "Shared" / "Downloads"
            downloads.mkdir(parents=True)
            config = home / ".config"
            config.mkdir()
            (config / "user-dirs.dirs").write_text(
                'XDG_DOWNLOAD_DIR="$HOME/Shared/Downloads"\n', encoding="utf-8"
            )
            self.assertEqual(default_export_directory(home), downloads)
            downloads.rmdir()
            self.assertEqual(default_export_directory(home), home)

    def test_export_never_overwrites_an_existing_capsule_name(self) -> None:
        snapshot = capsule_snapshot()
        with TemporaryDirectory() as directory:
            destination = Path(directory)
            with patch("xray.capsules.archive.datetime") as clock:
                clock.now.return_value.strftime.return_value = "20260821-120000"
                clock.now.return_value.isoformat.return_value = (
                    "2026-08-21T12:00:00+00:00"
                )
                first = export_capsule(snapshot, destination)
                first.write_bytes(b"keep-me")
                second = export_capsule(snapshot, destination)
            self.assertEqual(first.read_bytes(), b"keep-me")
            self.assertNotEqual(first, second)
            self.assertEqual(second.name, "omarchy-xray-20260821-120000-1.xray.zip")

    def test_export_load_and_compare_round_trip(self) -> None:
        snapshot = capsule_snapshot(processes=[{"id": "1:1"}])
        with TemporaryDirectory() as directory:
            path = export_capsule(snapshot, Path(directory), Path("/home/example"))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            payload = load_capsule(path)
            comparison = compare_capsule(snapshot, payload)
        self.assertEqual(comparison["domains"]["processes"], {"added": 0, "removed": 0})

    def test_import_rejects_extra_archive_members(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.xray.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("capsule.json", "{}")
                archive.writestr("other", "bad")
            with self.assertRaises(CapsuleError):
                load_capsule(path)

    def test_import_wraps_encrypted_or_unsupported_zip_read_failures(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "unsupported.xray.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("capsule.json", "{}")
            with (
                patch.object(
                    zipfile.ZipFile, "read", side_effect=RuntimeError("encrypted")
                ),
                self.assertRaisesRegex(CapsuleError, "not valid"),
            ):
                load_capsule(path)

    def test_import_rejects_non_finite_numbers(self) -> None:
        with self.assertRaises(CapsuleError):
            validate_snapshot(capsule_snapshot(metrics={"cpuPercent": float("nan")}))
        with self.assertRaises(CapsuleError):
            validate_snapshot(capsule_snapshot(metrics={"cpuPercent": float("inf")}))

    def test_import_revalidates_privacy_and_rejects_deep_structures(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "crafted.xray.zip"
            payload = {
                "capsuleSchema": CAPSULE_SCHEMA,
                "snapshotSchema": SCHEMA_VERSION,
                "snapshot": capsule_snapshot(
                    target={"label": '<img src="https://example.com/tracker">'},
                    context={"previewPath": "/etc/passwd"},
                ),
            }
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("capsule.json", json.dumps(payload))
            loaded = load_capsule(path)
            self.assertNotIn("previewPath", loaded["snapshot"]["context"])
            self.assertIn("<img", loaded["snapshot"]["target"]["label"])

            nested: object = "value"
            for _ in range(40):
                nested = {"child": nested}
            payload["snapshot"] = capsule_snapshot(nested=nested)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("capsule.json", json.dumps(payload))
            with self.assertRaises(CapsuleError):
                load_capsule(path)

    def test_import_rejects_domain_shapes_that_can_break_the_ui(self) -> None:
        with self.assertRaisesRegex(CapsuleError, "processes"):
            validate_snapshot(capsule_snapshot(processes={}))
        with self.assertRaisesRegex(CapsuleError, "devices.gpu"):
            validate_snapshot(
                capsule_snapshot(
                    devices={
                        "pipewire": [],
                        "gpu": "crafted",
                        "inhibitors": [],
                        "availability": {},
                    }
                )
            )
        with self.assertRaisesRegex(CapsuleError, "coverage"):
            validate_snapshot(
                capsule_snapshot(coverage={"available": [], "limited": "crafted"})
            )
        invalid_nested = (
            ("target.alternatives", {"target": {"alternatives": {}}}),
            ("target.trail", {"target": {"trail": {}}}),
            ("processes.command", {"processes": [{"command": {}}]}),
            ("context.cause.nodes", {"context": {"cause": {"nodes": {}}}}),
            ("context.container.ports", {"context": {"container": {"ports": {}}}}),
            ("security.namespaces", {"security": {"namespaces": []}}),
            ("security.limits", {"security": {"limits": {}}}),
            ("security.limits", {"security": {"limits": [None]}}),
            ("explanations.evidence", {"explanations": [{"evidence": {}}]}),
        )
        for label, override in invalid_nested:
            with (
                self.subTest(label=label),
                self.assertRaisesRegex(CapsuleError, label.replace(".", r"\.")),
            ):
                validate_snapshot(capsule_snapshot(**override))

    def test_maximum_file_domain_export_can_always_be_loaded_again(self) -> None:
        files = [
            {"pid": 1, "fd": index, "target": f"/tmp/{index}", "kind": "file"}
            for index in range(12_000)
        ]
        with TemporaryDirectory() as directory:
            path = export_capsule(
                capsule_snapshot(files=files), Path(directory), Path("/home/example")
            )
            loaded = load_capsule(path)
        self.assertEqual(len(loaded["snapshot"]["files"]), 12_000)

    def test_pathological_json_is_rejected_before_object_graph_allocation(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "crafted.xray.zip"
            raw = (
                b'{"capsuleSchema":1,"snapshotSchema":1,"snapshot":['
                + (b"0," * 200_001)
                + b"0]}"
            )
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("capsule.json", raw)
            with (
                patch("xray.capsules.archive.json.loads", MagicMock()) as loads,
                self.assertRaisesRegex(CapsuleError, "structure exceeds"),
            ):
                load_capsule(path)
            loads.assert_not_called()

    def test_capsule_loader_rejects_symlinks_and_special_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = export_capsule(capsule_snapshot(), root, Path("/home/example"))
            link = root / "linked.xray.zip"
            link.symlink_to(target)
            fifo = root / "stream.xray.zip"
            os.mkfifo(fifo)

            with self.assertRaises(CapsuleError):
                load_capsule(link)
            with self.assertRaisesRegex(CapsuleError, "missing or exceeds"):
                load_capsule(fifo)


if __name__ == "__main__":
    unittest.main()
