from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from typing import Collection, Mapping, Sequence

from support.markers import parse_json_marker
from support.paths import PROJECT_ROOT

QUICKSHELL = shutil.which("quickshell") or shutil.which("qs")
OMARCHY_IMPORTS = Path("/usr/share/omarchy/shell")
DRAWER_ENVIRONMENT_KEYS = frozenset(
    {"XRAY_DRAWER_DOMAIN", "XRAY_DRAWER_SECTION"}
)


@dataclass(frozen=True)
class QuickshellResult:
    returncode: int
    output: str

    def json_marker(self, marker_name: str) -> dict[str, object]:
        return parse_json_marker(self.output, marker_name)


class QuickshellHarness:
    """Stages and runs production QML in an isolated Quickshell configuration."""

    executable = QUICKSHELL
    imports = OMARCHY_IMPORTS
    project_root = PROJECT_ROOT

    @property
    def available(self) -> bool:
        return bool(
            self.executable
            and os.environ.get("WAYLAND_DISPLAY")
            and self.imports.is_dir()
        )

    def stage_plugin(
        self,
        root: Path,
        oracle: Path,
        *,
        include_backend: bool = False,
        entrypoints: Sequence[str] = (),
    ) -> Path:
        config = root / "config"
        config.mkdir()
        shutil.copy2(oracle, config / "shell.qml")
        shutil.copytree(self.project_root / "ui", config / "ui")
        if include_backend:
            shutil.copytree(self.project_root / "backend", config / "backend")
        for name in entrypoints:
            shutil.copy2(self.project_root / name, config / name)
        shutil.copytree(self.imports / "Commons", config / "Commons")
        shutil.copytree(self.imports / "Ui", config / "Ui")
        return config / "shell.qml"

    def run(
        self,
        shell: Path,
        *,
        timeout: float,
        environment: Mapping[str, str] | None = None,
        unset_environment: Collection[str] = (),
        state_home: Path | None = None,
    ) -> QuickshellResult:
        if not self.executable:
            raise RuntimeError("quickshell or qs is required")
        process_environment = dict(os.environ)
        for key in unset_environment:
            process_environment.pop(key, None)
        process_environment.update(environment or {})
        if state_home is not None:
            process_environment["XDG_STATE_HOME"] = str(state_home)
        completed = subprocess.run(
            [str(self.executable), "--path", str(shell)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=process_environment,
        )
        return QuickshellResult(
            returncode=completed.returncode,
            output=completed.stdout + "\n" + completed.stderr,
        )
