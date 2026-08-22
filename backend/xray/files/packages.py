from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from xray.config import LIMITS


def _section_contains(path: Path, name: str, expected: str) -> bool:
    marker = f"%{name}%"
    in_section = False
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if line == marker:
                in_section = True
            elif in_section and line.startswith("%") and line.endswith("%"):
                return False
            elif in_section and line == expected:
                return True
    return False


def _first_section_value(path: Path, name: str) -> str:
    marker = f"%{name}%"
    in_section = False
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if line == marker:
                in_section = True
            elif in_section and line.startswith("%") and line.endswith("%"):
                return ""
            elif in_section and line:
                return line
    return ""


@dataclass(frozen=True)
class PackageRecord:
    name: str
    version: str


class PackageIndex:
    """Resolve exact file owners from Arch's local package database."""

    def __init__(
        self,
        root: Path = Path("/var/lib/pacman/local"),
        cache_entries: int = LIMITS.package_owner_cache_entries,
    ) -> None:
        self.root = root
        self.cache_entries = max(1, cache_entries)
        self._owners: OrderedDict[str, PackageRecord | None] = OrderedDict()
        self._root_mtime_ns = -1

    def owner(self, path: str) -> PackageRecord | None:
        if not path.startswith("/"):
            return None
        normalized = path.lstrip("/")
        self._invalidate_if_changed()
        if normalized in self._owners:
            self._owners.move_to_end(normalized)
            return self._owners[normalized]
        owner = self._lookup(normalized)
        self._owners[normalized] = owner
        if len(self._owners) > self.cache_entries:
            self._owners.popitem(last=False)
        return owner

    def _invalidate_if_changed(self) -> None:
        try:
            root_mtime_ns = self.root.stat().st_mtime_ns
        except OSError:
            self._owners.clear()
            self._root_mtime_ns = -1
            return
        if root_mtime_ns == self._root_mtime_ns:
            return
        self._owners.clear()
        self._root_mtime_ns = root_mtime_ns

    def _lookup(self, normalized: str) -> PackageRecord | None:
        try:
            package_dirs = tuple(self.root.iterdir())
        except OSError:
            return None
        for directory in package_dirs:
            try:
                owns_path = _section_contains(directory / "files", "FILES", normalized)
            except OSError:
                continue
            if not owns_path:
                continue
            try:
                name = _first_section_value(directory / "desc", "NAME")
                version = _first_section_value(directory / "desc", "VERSION")
            except OSError:
                continue
            if not name:
                continue
            return PackageRecord(name, version)
        return None
