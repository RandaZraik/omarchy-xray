from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from xray.files.packages import PackageIndex
from xray.runtime.context import git_context


class SystemTruthTests(unittest.TestCase):
    @unittest.skipUnless(
        shutil.which("pacman"), "requires pacman as an independent package oracle"
    )
    def test_package_owner_and_version_match_pacman(self) -> None:
        executable = Path(shutil.which("python3") or "/usr/bin/python3")
        package_name = subprocess.run(
            ["pacman", "-Qqo", str(executable)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        package_line = subprocess.run(
            ["pacman", "-Q", package_name],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        expected_name, expected_version = package_line.split(maxsplit=1)

        observed = PackageIndex().owner(str(executable))
        self.assertIsNotNone(observed)
        self.assertEqual(
            (observed.name, observed.version), (expected_name, expected_version)
        )

    @unittest.skipUnless(
        shutil.which("git"), "requires git as an independent repository oracle"
    )
    def test_direct_git_context_matches_git_for_linked_and_regular_worktrees(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            worktree = Path(directory) / "worktree"
            subprocess.run(
                ["git", "init", "-b", "truth", str(repository)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.name", "X-Ray Truth"],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "config",
                    "user.email",
                    "truth@example.invalid",
                ],
                check=True,
            )
            (repository / "known.txt").write_text("truth\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repository), "add", "known.txt"], check=True
            )
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-m", "truth"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "worktree",
                    "add",
                    "-b",
                    "linked",
                    str(worktree),
                ],
                check=True,
                capture_output=True,
            )

            for path in (repository, worktree):
                expected = subprocess.run(
                    ["git", "-C", str(path), "branch", "--show-current"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                observed = git_context(str(path))
                self.assertEqual(observed["root"], str(path))
                self.assertEqual(observed["branch"], expected)


if __name__ == "__main__":
    unittest.main()
