import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock

from xray.runtime.context import (
    authoritative_window,
    cgroup_context,
    git_context,
    list_windows,
    normalize_window,
    window_for_processes,
)
from xray.runtime.security import (
    collect_logs,
    collect_security,
    decode_capabilities,
    mapped_libraries,
    parse_limits,
)
from xray.system.commands import CommandResult
from xray.system.procfs import ProcFs


class RuntimeTests(unittest.TestCase):
    def test_malformed_hyprland_inventory_is_reported_unavailable(self) -> None:
        runner = MagicMock()
        runner.run.return_value = CommandResult(("hyprctl",), 0, "not-json", "")

        windows, error = list_windows(runner)

        self.assertEqual(windows, [])
        self.assertEqual(error, "Hyprland window data is unavailable")

    def test_malformed_optional_window_numbers_do_not_break_the_inventory(self) -> None:
        window = normalize_window(
            {
                "pid": 41,
                "at": [None, "invalid"],
                "size": ["wide", {}],
                "focusHistoryID": [],
            }
        )

        self.assertEqual(
            {key: window[key] for key in ("x", "y", "width", "height")},
            {"x": 0, "y": 0, "width": 0, "height": 0},
        )
        self.assertEqual(window["focusOrder"], -1)

    def test_cgroup_extracts_unit_and_container_context(self) -> None:
        data = cgroup_context(
            "0::/user.slice/user-1000.slice/app.slice/app-org.example.Editor-123.scope\n"
        )
        self.assertEqual(data["unit"], "app-org.example.Editor-123.scope")
        container = cgroup_context("0::/user.slice/libpod-abcdef1234567890.scope\n")
        self.assertEqual(container["container"], "abcdef123456")

    def test_git_context_does_not_spawn_git(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / ".git/HEAD").write_text(
                "ref: refs/heads/master\n", encoding="utf-8"
            )
            (root / "src").mkdir()
            context = git_context(str(root / "src"))
        self.assertEqual(context["branch"], "master")

    def test_git_context_rejects_oversized_control_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / ".git/HEAD").write_text("x" * 5000, encoding="utf-8")
            self.assertEqual(git_context(str(root)), {"root": str(root), "branch": ""})

            (root / ".git/HEAD").unlink()
            (root / ".git").rmdir()
            (root / ".git").write_text("gitdir: " + "x" * 5000, encoding="utf-8")
            self.assertEqual(git_context(str(root)), {})

    def test_git_context_never_follows_repository_metadata_symlinks(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / "secret"
            secret.write_text("ref: refs/heads/leaked\n", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git/HEAD").symlink_to(secret)
            self.assertEqual(git_context(str(root)), {"root": str(root), "branch": ""})

            (root / ".git/HEAD").unlink()
            (root / ".git").rmdir()
            (root / ".git").symlink_to(root)
            self.assertEqual(git_context(str(root)), {})

    def test_cgroup_recognizes_containerd_and_nerdctl_ids(self) -> None:
        for marker in ("containerd", "cri-containerd", "nerdctl"):
            context = cgroup_context(
                f"0::/system.slice/{marker}-abcdef1234567890.scope\n"
            )
            self.assertEqual(context["container"], "abcdef123456")

    def test_window_matching_prefers_focused_descendant(self) -> None:
        windows = [
            normalize_window(
                {"pid": 10, "title": "A", "address": "0x1", "focusHistoryID": 3}
            ),
            normalize_window(
                {"pid": 11, "title": "B", "address": "0x2", "focusHistoryID": 0}
            ),
        ]
        self.assertEqual(window_for_processes(windows, [10, 11])["title"], "B")

    def test_explicit_window_address_cannot_drift_to_a_sibling_workspace(self) -> None:
        inferred = {"address": "0x1", "pid": 40, "workspace": {"id": 1}}
        selected = {"address": "0x2", "pid": 40, "workspace": {"id": 2}}
        self.assertEqual(authoritative_window(inferred, selected), selected)
        self.assertEqual(authoritative_window(inferred, {}), inferred)

    def test_security_parsers(self) -> None:
        self.assertEqual(decode_capabilities("20"), ["KILL"])
        limits = parse_limits(
            "Limit                     Soft Limit           Hard Limit           Units\nMax open files            1024                 4096                 files\n"
        )
        self.assertEqual(limits[0]["soft"], "1024")
        libraries = mapped_libraries(
            "7f-8f r-xp 0000 08:01 1 /usr/lib/libssl.so.3\n8f-9f rw-p 0000 00:00 0 [heap]\n"
        )
        self.assertEqual(libraries, ["/usr/lib/libssl.so.3"])

    def test_limits_handle_rows_without_a_units_column(self) -> None:
        text = (
            "Limit                     Soft Limit           Hard Limit           Units\n"
            "Max open files            1024                 4096                 files\n"
            "Max nice priority         0                    0\n"
        )
        self.assertEqual(
            parse_limits(text),
            [
                {
                    "name": "Max open files",
                    "soft": "1024",
                    "hard": "4096",
                    "unit": "files",
                },
                {"name": "Max nice priority", "soft": "0", "hard": "0", "unit": ""},
            ],
        )

    def test_journal_rows_are_bounded_to_the_process_start_time(self) -> None:
        runner = MagicMock()
        runner.run.return_value = CommandResult(
            ("journalctl",),
            0,
            "\n".join(
                [
                    '{"__REALTIME_TIMESTAMP":"999999","PRIORITY":"3","MESSAGE":"old"}',
                    '{"__REALTIME_TIMESTAMP":"1000001","PRIORITY":"3","MESSAGE":"current token=secret"}',
                ]
            ),
            "",
        )
        rows, limited = collect_logs(runner, 41, 1.0)

        self.assertEqual(limited, "")
        self.assertEqual([row["message"] for row in rows], ["current token=<redacted>"])
        self.assertIn("--since=@1", runner.run.call_args.args[0])

        collect_logs(runner, 41, 1.0, scope="system")
        self.assertNotIn("--user", runner.run.call_args.args[0])

        runner.run.return_value = CommandResult(
            ("journalctl",), 1, "", "permission denied"
        )
        rows, limited = collect_logs(runner, 41, 1.0)
        self.assertEqual(rows, [])
        self.assertEqual(limited, "Journal entries are unavailable")

    def test_journal_redacts_before_truncating_long_private_material(self) -> None:
        runner = MagicMock()
        secret = "-----BEGIN PRIVATE KEY-----\n" + "A" * 5000
        runner.run.return_value = CommandResult(
            ("journalctl",),
            0,
            '{"__REALTIME_TIMESTAMP":"1000001","MESSAGE":' + json.dumps(secret) + "}",
            "",
        )

        rows, limited = collect_logs(runner, 41, 1.0)

        self.assertEqual(limited, "")
        self.assertEqual(rows[0]["message"], "<redacted private key>")

    def test_security_collection_declares_mapped_library_truncation(self) -> None:
        with TemporaryDirectory() as directory:
            process = Path(directory) / "7"
            (process / "attr").mkdir(parents=True)
            (process / "ns").mkdir()
            (process / "status").write_text(
                "Uid:\t1000\nGid:\t1000\nCapEff:\t0\n", encoding="utf-8"
            )
            (process / "attr/current").write_text("unconfined\n", encoding="utf-8")
            (process / "limits").write_text(
                "Limit  Soft Limit  Hard Limit  Units\n", encoding="utf-8"
            )
            (process / "maps").write_text(
                "".join(
                    f"7f-8f r-xp 0000 08:01 {index} /usr/lib/lib{index}.so\n"
                    for index in range(302)
                ),
                encoding="utf-8",
            )
            (process / "oom_score").write_text("10\n", encoding="utf-8")
            (process / "oom_score_adj").write_text("0\n", encoding="utf-8")
            security, limited = collect_security(ProcFs(Path(directory)), 7)

        self.assertEqual(len(security["libraries"]), 300)
        self.assertIn("Mapped libraries are limited to 300 entries", limited)

    def test_unavailable_process_status_never_claims_security_is_disabled(self) -> None:
        security, limited = collect_security(ProcFs(Path("/missing")), 999999)

        self.assertFalse(security["statusAvailable"])
        self.assertEqual(security["seccomp"], "Unknown")
        self.assertIsNone(security["noNewPrivileges"])
        self.assertFalse(security["capabilitiesKnown"])
        self.assertIsNone(security["oomScore"])
        self.assertIsNone(security["oomAdjustment"])
        self.assertTrue(limited)
        self.assertTrue(
            any("AppArmor/LSM label unavailable" in value for value in limited)
        )


if __name__ == "__main__":
    unittest.main()
