from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

from xray import SCHEMA_VERSION
from xray.config import CAPSULE_SCHEMA, LIMITS
from xray.evidence.redaction import redact_snapshot
from xray.evidence.changes import compare_snapshots


class CapsuleError(ValueError):
    pass


_SNAPSHOT_OBJECTS = (
    "target",
    "context",
    "metrics",
    "devices",
    "security",
    "coverage",
    "changes",
    "settings",
)
_SNAPSHOT_LISTS = (
    "processes",
    "connections",
    "files",
    "locks",
    "logs",
    "actions",
    "explanations",
    "timeline",
)


def validate_snapshot(snapshot: object) -> dict[str, object]:
    if not isinstance(snapshot, dict):
        raise CapsuleError("Capsule does not contain a snapshot")
    _validate_structure(snapshot)
    _validate_domains(snapshot)
    _validate_nested_domains(snapshot)
    return snapshot


def _validate_structure(snapshot: dict[str, object]) -> None:
    pending: list[tuple[object, int]] = [(snapshot, 0)]
    visited = 0
    while pending:
        value, depth = pending.pop()
        visited += 1
        if visited > LIMITS.capsule_nodes or depth > LIMITS.capsule_depth:
            raise CapsuleError("Capsule structure exceeds the safety limit")
        if isinstance(value, dict):
            if not all(isinstance(key, str) for key in value):
                raise CapsuleError("Capsule contains an invalid object key")
            if len(value) > LIMITS.capsule_nodes - visited:
                raise CapsuleError("Capsule structure exceeds the safety limit")
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            if len(value) > LIMITS.capsule_nodes - visited:
                raise CapsuleError("Capsule structure exceeds the safety limit")
            pending.extend((child, depth + 1) for child in value)
        elif (
            isinstance(value, str)
            and len(value.encode("utf-8")) > LIMITS.capsule_string_bytes
        ):
            raise CapsuleError("Capsule contains an oversized text value")
        elif isinstance(value, float) and not math.isfinite(value):
            raise CapsuleError("Capsule contains a non-finite number")
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise CapsuleError("Capsule contains an unsupported value")


def _validate_domains(snapshot: dict[str, object]) -> None:
    if snapshot.get("schema") != SCHEMA_VERSION:
        raise CapsuleError("Capsule snapshot schema is not supported")
    for key in _SNAPSHOT_OBJECTS:
        if not isinstance(snapshot.get(key), dict):
            raise CapsuleError(f"Capsule snapshot has an invalid {key} domain")
    for key in _SNAPSHOT_LISTS:
        rows = snapshot.get(key)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise CapsuleError(f"Capsule snapshot has an invalid {key} domain")
    devices = snapshot["devices"]
    for key in ("pipewire", "gpu", "inhibitors"):
        rows = devices.get(key)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise CapsuleError(f"Capsule snapshot has an invalid devices.{key} domain")
    if not isinstance(devices.get("availability"), dict):
        raise CapsuleError("Capsule snapshot has an invalid device availability")
    coverage = snapshot["coverage"]
    if not all(isinstance(coverage.get(key), list) for key in ("available", "limited")):
        raise CapsuleError(
            "Capsule snapshot has invalid data availability details (coverage)"
        )


def _validate_nested_domains(snapshot: dict[str, object]) -> None:
    target = snapshot["target"]
    if "alternatives" in target and not _dict_list(target["alternatives"]):
        raise CapsuleError("Capsule snapshot has invalid target.alternatives")
    if "trail" in target and not _dict_list(target["trail"]):
        raise CapsuleError("Capsule snapshot has invalid target.trail")
    for row in snapshot["processes"]:
        if "command" in row and not isinstance(row["command"], list):
            raise CapsuleError("Capsule snapshot has invalid processes.command")

    context = snapshot["context"]
    for key in ("window", "service", "container", "cause"):
        if key in context and not isinstance(context[key], dict):
            raise CapsuleError(f"Capsule snapshot has invalid context.{key}")
    cause = context.get("cause", {})
    if "nodes" in cause and not _dict_list(cause["nodes"]):
        raise CapsuleError("Capsule snapshot has invalid context.cause.nodes")
    service = context.get("service", {})
    if "triggeredBy" in service and not isinstance(service["triggeredBy"], list):
        raise CapsuleError("Capsule snapshot has invalid context.service.triggeredBy")
    container = context.get("container", {})
    for key in ("ports", "mounts", "networks"):
        if key in container and not _dict_list(container[key]):
            raise CapsuleError(f"Capsule snapshot has invalid context.container.{key}")

    security = snapshot["security"]
    if "namespaces" in security and not isinstance(security["namespaces"], dict):
        raise CapsuleError("Capsule snapshot has invalid security.namespaces")
    if "limits" in security and not _dict_list(security["limits"]):
        raise CapsuleError("Capsule snapshot has invalid security.limits")
    for key in ("libraries", "capabilities"):
        if key in security and not isinstance(security[key], list):
            raise CapsuleError(f"Capsule snapshot has invalid security.{key}")
    for row in snapshot["explanations"]:
        if "evidence" in row and not isinstance(row["evidence"], list):
            raise CapsuleError(
                "Capsule snapshot has invalid explanation source details "
                "(explanations.evidence)"
            )


def _dict_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(row, dict) for row in value)


def default_export_directory(home: Path | None = None) -> Path:
    home_path = home or Path.home()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", home_path / ".config"))
    user_dirs = config_home / "user-dirs.dirs"
    try:
        content = user_dirs.read_text(encoding="utf-8", errors="replace")
    except OSError:
        content = ""
    match = re.search(r'^XDG_DOWNLOAD_DIR="([^"]*)"$', content, re.MULTILINE)
    configured = match.group(1).replace("$HOME", str(home_path)) if match else ""
    candidate = Path(configured).expanduser() if configured else home_path / "Downloads"
    return candidate if candidate.is_dir() else home_path


def capsule_payload(
    snapshot: dict[str, object], home: Path | None = None
) -> dict[str, object]:
    sanitized = redact_snapshot(snapshot, home)
    validate_snapshot(sanitized)
    return {
        "capsuleSchema": CAPSULE_SCHEMA,
        "snapshotSchema": SCHEMA_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "snapshot": sanitized,
    }


def export_capsule(
    snapshot: dict[str, object], directory: Path, home: Path | None = None
) -> Path:
    directory = directory.expanduser().resolve(strict=True)
    if not directory.is_dir():
        raise CapsuleError("Export destination is not a directory")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    payload = json.dumps(
        capsule_payload(snapshot, home), ensure_ascii=False, indent=2
    ).encode("utf-8")
    if len(payload) > LIMITS.capsule_json_bytes:
        raise CapsuleError("Capsule exceeds the size limit")
    fd, temporary_name = tempfile.mkstemp(prefix=".xray-", suffix=".zip", dir=directory)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        os.close(fd)
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr("capsule.json", payload)
        target = _reserve_export_path(directory, stamp)
        try:
            os.replace(temporary, target)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    except Exception:
        with suppress(OSError):
            os.close(fd)
        temporary.unlink(missing_ok=True)
        raise
    return target


def _reserve_export_path(directory: Path, stamp: str) -> Path:
    suffix = 0
    while True:
        discriminator = f"-{suffix}" if suffix else ""
        candidate = directory / f"omarchy-xray-{stamp}{discriminator}.xray.zip"
        try:
            descriptor = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            suffix += 1
            continue
        os.close(descriptor)
        return candidate


def load_capsule(path: Path) -> dict[str, object]:
    try:
        descriptor = os.open(
            path.expanduser(),
            os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(descriptor, "rb") as source:
            metadata = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size > LIMITS.capsule_bytes
            ):
                raise CapsuleError("Capsule is missing or exceeds the size limit")
            archive_bytes = source.read(LIMITS.capsule_bytes + 1)
        if len(archive_bytes) > LIMITS.capsule_bytes:
            raise CapsuleError("Capsule is missing or exceeds the size limit")
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            if archive.namelist() != ["capsule.json"]:
                raise CapsuleError("Capsule has an unexpected file layout")
            info = archive.getinfo("capsule.json")
            if info.file_size > LIMITS.capsule_json_bytes:
                raise CapsuleError("Capsule content exceeds the size limit")
            raw = archive.read(info)
            _preflight_json(raw)
            payload = json.loads(raw.decode("utf-8"))
    except CapsuleError:
        raise
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        NotImplementedError,
        RecursionError,
        RuntimeError,
        zipfile.BadZipFile,
    ) as error:
        raise CapsuleError("Capsule is not valid") from error
    if (
        not isinstance(payload, dict)
        or payload.get("capsuleSchema") != CAPSULE_SCHEMA
        or payload.get("snapshotSchema") != SCHEMA_VERSION
    ):
        raise CapsuleError("Capsule schema is not supported")
    payload["snapshot"] = redact_snapshot(validate_snapshot(payload.get("snapshot")))
    return payload


def _preflight_json(raw: bytes) -> None:
    """Reject pathological object graphs before json.loads allocates them."""
    structural = 0
    depth = 0
    in_string = False
    escaped = False
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x7B, 0x5B):
            structural += 1
            depth += 1
            if depth > LIMITS.capsule_depth:
                raise CapsuleError("Capsule structure exceeds the safety limit")
        elif byte in (0x7D, 0x5D):
            depth -= 1
            if depth < 0:
                raise CapsuleError("Capsule is not valid")
        elif byte == 0x2C:
            structural += 1
        if structural > LIMITS.capsule_nodes:
            raise CapsuleError("Capsule structure exceeds the safety limit")
    if in_string or depth != 0:
        raise CapsuleError("Capsule is not valid")


def compare_capsule(
    snapshot: dict[str, object], payload: dict[str, object]
) -> dict[str, object]:
    archived = validate_snapshot(payload.get("snapshot"))
    return compare_snapshots(archived, redact_snapshot(snapshot))
