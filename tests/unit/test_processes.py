from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import os
import unittest
from unittest.mock import patch

from xray.processes.collector import (
    ProcessMetadataCache,
    collect_tree,
    descendant_pids,
    user_name,
)
from xray.processes.identity import parse_stat, same_user_pids
from xray.processes.identity import ProcessIdentity
from xray.config import LIMITS
from xray.system.procfs import ProcFs
from support.procfs import stat_line, write_process


class ProcessTests(unittest.TestCase):
    def tearDown(self) -> None:
        user_name.cache_clear()

    def test_stat_parser_handles_parentheses_in_name(self) -> None:
        parsed = parse_stat(stat_line(8, "renderer (gpu)", 2, 99))
        self.assertEqual(parsed["comm"], "renderer (gpu)")
        self.assertEqual(parsed["start_time"], 99)

    def test_descendants_are_bounded_and_cycle_safe(self) -> None:
        parents = {1: 3, 2: 1, 3: 2, 4: 2}
        self.assertEqual(descendant_pids(parents, 1, 4), [1, 2, 3, 4])

    def test_collect_tree_preserves_identity_and_never_exposes_env_values(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_process(
                root,
                10,
                "app",
                1,
                100,
                b"app\0--token\0secret\0",
                b"TOKEN=secret\0LANG=en\0",
            )
            self._write_process(
                root, 11, "child", 10, 110, b"child\0", b"PASSWORD=hidden\0"
            )
            collection = collect_tree(ProcFs(root), 10)

        self.assertEqual(collection.root_identity.key, "10:100")
        self.assertEqual([row["pid"] for row in collection.rows], [10, 11])
        self.assertEqual([row["depth"] for row in collection.rows], [0, 1])
        self.assertTrue(collection.rows[0]["user"])
        self.assertEqual(collection.rows[0]["environmentNames"], ["LANG", "TOKEN"])
        self.assertNotIn("secret", repr(collection.rows[0]))
        self.assertEqual(
            collection.rows[0]["command"], ["app", "--token", "<redacted>"]
        )

    def test_process_rows_include_a_human_user_name_with_numeric_fallback(self) -> None:
        user_name.cache_clear()
        with patch(
            "xray.processes.collector.pwd.getpwuid",
            return_value=SimpleNamespace(pw_name="demo-user"),
        ):
            self.assertEqual(user_name(1000), "demo-user")

        user_name.cache_clear()
        with patch("xray.processes.collector.pwd.getpwuid", side_effect=KeyError):
            self.assertEqual(user_name(4242), "4242")

    def test_process_memory_uses_the_same_stat_rss_counter_as_btop(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(
                root,
                10,
                "app",
                1,
                rss_pages=5,
                command=b"app\0",
                environ=b"",
                status_lines=("Threads:\t1", "VmRSS:\t999 kB"),
            )
            collection = collect_tree(ProcFs(root), 10)

        self.assertEqual(
            collection.rows[0]["memoryBytes"], 5 * os.sysconf("SC_PAGE_SIZE")
        )

    def test_zero_stat_rss_does_not_fall_back_to_status_memory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_process(
                root,
                10,
                "zombie",
                1,
                rss_pages=0,
                command=b"zombie\0",
                environ=b"",
                status_lines=("Threads:\t1", "VmRSS:\t999 kB"),
            )
            collection = collect_tree(ProcFs(root), 10)

        self.assertEqual(collection.rows[0]["memoryBytes"], 0)

    def test_live_tree_uses_kernel_children_without_a_global_process_scan(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_process(root, 10, "app", 1, 100, b"app\0", b"")
            self._write_process(root, 11, "child", 10, 110, b"child\0", b"")
            for pid, children in ((10, "11\n"), (11, "\n")):
                task = root / str(pid) / "task" / str(pid)
                task.mkdir(parents=True)
                (task / "children").write_text(children, encoding="utf-8")
            with patch(
                "xray.processes.collector.process_parent_map",
                side_effect=AssertionError("global scan should not run"),
            ):
                collection = collect_tree(ProcFs(root), 10)

        self.assertEqual([row["pid"] for row in collection.rows], [10, 11])

    def test_kernel_tree_includes_children_spawned_by_nonleader_threads(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_process(root, 10, "app", 1, 100, b"app\0", b"")
            self._write_process(root, 11, "child", 10, 110, b"child\0", b"")
            for pid, task, children in (
                (10, 10, ""),
                (10, 12, "11\n"),
                (11, 11, ""),
            ):
                task_path = root / str(pid) / "task" / str(task)
                task_path.mkdir(parents=True)
                (task_path / "children").write_text(children, encoding="utf-8")

            collection = collect_tree(ProcFs(root), 10)

        self.assertEqual([row["pid"] for row in collection.rows], [10, 11])

    def test_missing_process_returns_clear_limit(self) -> None:
        with TemporaryDirectory() as directory:
            collection = collect_tree(ProcFs(Path(directory)), 404)
        self.assertIsNone(collection.root_identity)
        self.assertIn("no longer available", collection.limited[0])

    def test_root_pid_replacement_during_collection_is_rejected(self) -> None:
        replacement = {
            "pid": 10,
            "startTime": 101,
            "uid": 1000,
        }
        with (
            patch(
                "xray.processes.collector.identity_for",
                return_value=ProcessIdentity(10, 100, 1000),
            ),
            patch("xray.processes.collector.process_parent_map", return_value={10: 1}),
            patch(
                "xray.processes.collector.collect_process",
                return_value=(replacement, ""),
            ),
        ):
            collection = collect_tree(ProcFs(Path("/missing")), 10)

        self.assertIsNone(collection.root_identity)
        self.assertEqual(collection.rows, [])
        self.assertIn("changed while it was inspected", collection.limited[0])

    def test_partial_child_status_is_declared_as_limited_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_process(root, 10, "app", 1, 100, b"app\0", b"")
            self._write_process(root, 11, "child", 10, 110, b"child\0", b"")
            (root / "11/status").unlink()
            collection = collect_tree(ProcFs(root), 10)

        self.assertEqual([row["pid"] for row in collection.rows], [10, 11])
        self.assertIn("Process 11 status is unavailable: not found", collection.limited)

    def test_reused_descendant_pid_cannot_enter_the_selected_tree(self) -> None:
        root_row = {"pid": 10, "ppid": 1, "startTime": 100, "uid": 1000}
        reused_child = {"pid": 11, "ppid": 99, "startTime": 999, "uid": 1000}
        with (
            patch(
                "xray.processes.collector.identity_for",
                return_value=ProcessIdentity(10, 100, 1000),
            ),
            patch(
                "xray.processes.collector.collect_process",
                side_effect=[(root_row, ""), (reused_child, "")],
            ),
        ):
            collection = collect_tree(
                ProcFs(Path("/missing")), 10, parent_map={10: 1, 11: 10}
            )

        self.assertEqual([row["pid"] for row in collection.rows], [10])
        self.assertIn("changed ancestry", collection.limited[0])

    def test_static_process_metadata_is_reused_for_the_same_identity(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_process(root, 10, "app", 1, 100, b"app\0--safe\0", b"LANG=en\0")
            metadata = ProcessMetadataCache()
            first = collect_tree(ProcFs(root), 10, metadata=metadata)
            for name in ("cmdline", "environ", "exe", "cwd"):
                (root / "10" / name).unlink()
            second = collect_tree(ProcFs(root), 10, metadata=metadata)

        self.assertEqual(second.rows[0]["command"], first.rows[0]["command"])
        self.assertEqual(second.rows[0]["environmentNames"], ["LANG"])
        self.assertEqual(second.rows[0]["executable"], "/usr/bin/example")

    def test_command_and_environment_metadata_are_bounded_and_declared(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            command = (
                b"\0".join(
                    f"arg-{index}".encode()
                    for index in range(LIMITS.process_command_arguments + 10)
                )
                + b"\0"
            )
            environment = b"X=" + b"x" * LIMITS.process_environment_bytes
            self._write_process(root, 10, "app", 1, 100, command, environment)
            collection = collect_tree(ProcFs(root), 10)

        self.assertEqual(
            len(collection.rows[0]["command"]), LIMITS.process_command_arguments
        )
        self.assertEqual(collection.rows[0]["environmentNames"], [])
        self.assertTrue(
            any("command line is limited" in value for value in collection.limited)
        )
        self.assertTrue(
            any(
                "environment names are unavailable" in value
                for value in collection.limited
            )
        )

    def test_cached_metadata_limitations_remain_visible_on_every_sample(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            command = (
                b"\0".join(
                    f"arg-{index}".encode()
                    for index in range(LIMITS.process_command_arguments + 1)
                )
                + b"\0"
            )
            self._write_process(root, 10, "app", 1, 100, command, b"")
            metadata = ProcessMetadataCache()
            first = collect_tree(ProcFs(root), 10, metadata=metadata)
            second = collect_tree(ProcFs(root), 10, metadata=metadata)

        for collection in (first, second):
            self.assertTrue(
                any("command line is limited" in value for value in collection.limited)
            )

    def test_same_user_catalog_excludes_other_uids_and_unreadable_processes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_process(root, 10, "mine", 1, 100, b"mine\0", b"")
            self._write_process(root, 11, "other", 1, 110, b"other\0", b"")
            (root / "11/status").write_text(
                "Name:\tother\nUid:\t2000 2000 2000 2000\n", encoding="utf-8"
            )
            (root / "12").mkdir()
            self.assertEqual(same_user_pids(ProcFs(root), uid=1000), [10])

    def _write_process(
        self,
        root: Path,
        pid: int,
        name: str,
        ppid: int,
        start: int,
        command: bytes,
        environ: bytes,
    ) -> None:
        write_process(
            root,
            pid,
            name,
            ppid,
            start=start,
            ticks=5,
            command=command,
            environ=environ,
            executable="/usr/bin/example",
            working_directory="/work/project",
            status_lines=("Threads:\t1", "VmRSS:\t12 kB"),
        )


if __name__ == "__main__":
    unittest.main()
