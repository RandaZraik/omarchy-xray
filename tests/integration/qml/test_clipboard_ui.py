import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from support.quickshell import PROJECT_ROOT, QuickshellHarness


HARNESS = QuickshellHarness()
ORACLE = Path(__file__).with_name("oracles") / "clipboard_oracle.qml"


@unittest.skipUnless(
    HARNESS.executable and HARNESS.imports.is_dir(),
    "requires Quickshell and Omarchy imports",
)
class ClipboardUiTests(unittest.TestCase):
    def test_foreign_offers_never_read_and_explicit_paste_stays_responsive(self):
        moc = Path("/usr/lib/qt6/moc")
        if (
            not moc.is_file()
            or not shutil.which("g++")
            or not shutil.which("pkg-config")
        ):
            self.skipTest(
                "requires Qt development tools for the foreign-clipboard probe"
            )
        flags = subprocess.run(
            ["pkg-config", "--cflags", "--libs", "Qt6Qml", "Qt6Gui"],
            capture_output=True,
            text=True,
        )
        if flags.returncode:
            self.skipTest(
                "requires Qt development headers for the foreign-clipboard probe"
            )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shell = HARNESS.stage_plugin(root, ORACLE, include_backend=True)
            module = root / "imports/XRayClipboardTest"
            module.mkdir(parents=True)
            source = module / "clipboard_probe.cpp"
            shutil.copy2(PROJECT_ROOT / "tests/support/clipboard_probe.cpp", source)
            build_flags = shlex.split(flags.stdout)
            for command in (
                [
                    str(moc),
                    *[flag for flag in build_flags if flag.startswith(("-I", "-D"))],
                    str(source),
                    "-o",
                    str(module / "clipboard_probe.moc"),
                ],
                [
                    "g++",
                    "-shared",
                    "-fPIC",
                    "-std=c++17",
                    str(source),
                    "-o",
                    str(module / "libclipboardprobe.so"),
                    *build_flags,
                ],
            ):
                built = subprocess.run(
                    command, capture_output=True, text=True, timeout=30
                )
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            (module / "qmldir").write_text(
                "module XRayClipboardTest\nplugin clipboardprobe\n"
            )
            commands = root / "bin"
            commands.mkdir()
            mode = root / "mode"
            mode.write_text("normal")
            calls = root / "calls"
            fake = commands / "wl-paste"
            fake.write_text(
                f"#!{sys.executable}\n"
                "from pathlib import Path\nimport os,time,sys\n"
                f"mode=Path({str(mode)!r}).read_text()\n"
                f"with Path({str(calls)!r}).open('a') as f: f.write(' '.join(sys.argv[1:])+'\\n')\n"
                "if mode=='slow': time.sleep(0.4)\n"
                "if mode=='stall':\n"
                "    while True: os.write(1,b'x'); time.sleep(0.02)\n"
                "print('x'*20000 if mode=='large' else 'مرحبا 🌍',end='')\n"
            )
            fake.chmod(0o700)
            result = HARNESS.run_offscreen(
                shell,
                timeout=25,
                state_home=root / "state",
                environment={
                    "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                    "QML_IMPORT_PATH": str(root / "imports"),
                    "XRAY_CLIPBOARD_MODE": str(mode),
                },
            )
            self.assertEqual(result.returncode, 0, result.output)
            marker = result.json_marker("XRAY_CLIPBOARD")
            self.assertGreater(marker["unguardedReads"], 0)
            self.assertEqual(marker["guardedReads"], 0)
            self.assertEqual(marker["fields"], 4)
            for key in (
                "editing",
                "undo",
                "paste",
                "primary",
                "oversized",
                "deadline",
                "stalePaste",
                "modelSync",
            ):
                self.assertTrue(marker[key], key)
            self.assertIn("--primary", calls.read_text())
            self.assertEqual(len(calls.read_text().splitlines()), 7)
