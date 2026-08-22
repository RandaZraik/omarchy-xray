from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest

from xray.files.open_files import (
    collect_open_files,
    descriptor_kind,
    parse_fdinfo,
    parse_locks,
    owners_for_file,
)
from xray.files.packages import PackageIndex
from xray.system.procfs import ProcFs
from xray.system.descriptors import Descriptor, DescriptorInventory


class FileTests(unittest.TestCase):
    def test_descriptor_kinds_and_fdinfo(self) -> None:
        self.assertEqual(descriptor_kind("socket:[12]"), "socket")
        self.assertEqual(descriptor_kind("/tmp/report"), "file")
        info = parse_fdinfo("pos:\t42\nflags:\t0100002\nmnt_id:\t7\n")
        self.assertEqual(info["mode"], "read/write")
        self.assertEqual(info["position"], 42)

    def test_locks_only_include_selected_processes(self) -> None:
        text = "1: POSIX ADVISORY WRITE 41 08:01:9 0 EOF\n2: FLOCK ADVISORY READ 99 08:01:3 0 EOF\n"
        self.assertEqual(parse_locks(text, {41})[0]["mode"], "Write")

    def test_ofd_locks_are_joined_through_selected_descriptor_identity(self) -> None:
        text = "1: OFDLCK ADVISORY WRITE -1 08:01:9 0 EOF\n"

        rows = parse_locks(text, {41}, {(8, 1, 9)})

        self.assertEqual(rows[0]["owner"], "OFD")
        self.assertEqual(rows[0]["pid"], -1)

    def test_collects_deleted_open_file_and_lock(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "41/fdinfo").mkdir(parents=True)
            (root / "41/fd").mkdir()
            (root / "41/fd/9").symlink_to("/tmp/report.log (deleted)")
            (root / "41/fdinfo/9").write_text(
                "pos:\t2\nflags:\t0100000\n", encoding="utf-8"
            )
            (root / "locks").write_text(
                "1: POSIX ADVISORY WRITE 41 08:01:9 0 EOF\n", encoding="utf-8"
            )
            evidence = collect_open_files(ProcFs(root), [41])

        self.assertTrue(evidence.rows[0]["deleted"])
        self.assertEqual(len(evidence.locks), 1)
        self.assertEqual(evidence.limited, ())
        self.assertTrue(evidence.files_complete)
        self.assertTrue(evidence.locks_available)

    def test_package_index_refreshes_when_local_database_changes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "demo-1.2-1"
            package.mkdir()
            (package / "desc").write_text(
                "%NAME%\ndemo\n\n%VERSION%\n1.2-1\n", encoding="utf-8"
            )
            (package / "files").write_text(
                "%FILES%\nusr/bin/demo\nusr/share/demo/\n", encoding="utf-8"
            )
            index = PackageIndex(root)
            owner = index.owner("/usr/bin/demo")
            self.assertIsNone(index.owner("/usr/bin/demonstration"))
            for path in package.iterdir():
                path.unlink()
            package.rmdir()
            os.utime(root, ns=(root.stat().st_atime_ns, root.stat().st_mtime_ns + 1))
            removed = index.owner("/usr/bin/demo")
        self.assertEqual(owner.name, "demo")
        self.assertEqual(owner.version, "1.2-1")
        self.assertIsNone(removed)

    def test_package_index_is_optional_on_non_arch_hosts(self) -> None:
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "pacman-local"

            self.assertIsNone(PackageIndex(missing).owner("/usr/bin/demo"))

    def test_package_owner_cache_is_bounded_and_keeps_negative_results(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "demo-1.2-1"
            package.mkdir()
            (package / "desc").write_text(
                "%NAME%\ndemo\n\n%VERSION%\n1.2-1\n", encoding="utf-8"
            )
            (package / "files").write_text("%FILES%\nusr/bin/demo\n", encoding="utf-8")
            index = PackageIndex(root, cache_entries=2)

            self.assertEqual(index.owner("/usr/bin/demo").name, "demo")
            self.assertIsNone(index.owner("/missing/one"))
            self.assertIsNone(index.owner("/missing/two"))

        self.assertEqual(list(index._owners), ["missing/one", "missing/two"])

    def test_unavailable_kernel_lock_table_is_declared(self) -> None:
        evidence = collect_open_files(ProcFs(Path("/missing")), [])

        self.assertEqual(evidence.rows, [])
        self.assertEqual(evidence.locks, [])
        self.assertFalse(evidence.locks_available)
        self.assertTrue(
            any(
                message.startswith("Kernel lock table is unavailable")
                for message in evidence.limited
            )
        )

    def test_unavailable_fdinfo_marks_file_evidence_incomplete(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "41/fd").mkdir(parents=True)
            (root / "41/fd/9").symlink_to("/tmp/report.log")
            (root / "locks").write_text("", encoding="utf-8")
            evidence = collect_open_files(ProcFs(root), [41])

        self.assertEqual(len(evidence.rows), 1)
        self.assertFalse(evidence.files_complete)
        self.assertTrue(
            any(
                "Open file metadata is unavailable" in value
                for value in evidence.limited
            )
        )

    def test_recreated_path_does_not_match_a_deleted_old_inode(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recreated.txt"
            path.write_text("old", encoding="utf-8")
            descriptor = os.open(path, os.O_RDONLY)
            try:
                path.unlink()
                path.write_text("new", encoding="utf-8")
                pid = os.getpid()
                target = os.readlink(f"/proc/{pid}/fd/{descriptor}")
                inventory = DescriptorInventory(
                    (Descriptor(pid, descriptor, str(descriptor), target),), ()
                )
                owners = owners_for_file(ProcFs(), path, inventory)
            finally:
                os.close(descriptor)

        self.assertEqual(owners, [])


if __name__ == "__main__":
    unittest.main()
