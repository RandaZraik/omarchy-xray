from __future__ import annotations

import ipaddress
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit


_SECRET_FLAG = re.compile(
    r"^(?:--?)?(?:api[-_]?key|access[-_]?(?:key|token)|account[-_]?key|auth(?:[-_]?token)?|authorization|password|passwd|passphrase|secret|token|client[-_]?secret|private[-_]?key|credential|cookie|session|pgpassword|mysql[-_]?pwd|connection[-_]?string)$",
    re.IGNORECASE,
)
_SECRET_NAME_PART = re.compile(
    r"(?:^|[-_])(?:api[-_]?key|access[-_]?(?:key|token)|account[-_]?key|auth(?:[-_]?token)?|authorization|password|passwd|passphrase|secret(?:[-_]?access[-_]?key)?|token|client[-_]?secret|private[-_]?key|credential|cookie|session|database[-_]?url|pgpassword|mysql[-_]?pwd|connection[-_]?string)(?:$|[-_])",
    re.IGNORECASE,
)
_ASSIGNMENT = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_.-]*|--?[A-Za-z][A-Za-z0-9_.-]*)=(.*)$", re.DOTALL
)
_EMBEDDED_SECRET = re.compile(
    r"(?i)((?<![A-Za-z0-9])([\"']?)(?:api[-_ ]?key|access[-_ ]?(?:key|token)|account[-_ ]?key|auth(?:[-_ ]?token)?|authorization|password|passwd|passphrase|secret(?:[-_ ]?access[-_ ]?key)?|token|client[-_ ]?secret|private[-_ ]?key|credential|cookie|session|database[-_ ]?url|pgpassword|mysql[-_ ]?pwd|connection[-_ ]?string)\2(?![A-Za-z0-9])\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)
_EMBEDDED_URL = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s<>'\"]+")
_SENSITIVE_HEADER = re.compile(
    r"(?i)(\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*:\s*)[^\r\n]+"
)
_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?![A-Za-z0-9_-])"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?P<key_type>[A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?)-----"
    r".*?(?:-----END (?P=key_type)-----|$)",
    re.DOTALL,
)
_COMMAND_LIST_KEYS = frozenset({"command", "entrypoint"})
_COMMAND_SECRET_FLAGS = {
    "curl": ("--oauth2-bearer", "--pass", "--proxy-user", "--user", "-u"),
    "gpg": ("--passphrase",),
    "gpg2": ("--passphrase",),
    "mariadb": ("--password", "-p"),
    "mysql": ("--password", "-p"),
    "mysqldump": ("--password", "-p"),
    "redis-cli": ("--pass", "-a"),
    "sshpass": ("-p",),
    "openssl": ("-passin", "-passout", "-pass"),
}


def _normalize_secret_name(value: str) -> str:
    without_prefix = value[2:] if value.startswith("-D") else value.lstrip("-")
    with_boundaries = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", without_prefix)
    return re.sub(r"[. ]+", "-", with_boundaries)


def _is_secret_name(value: str) -> bool:
    normalized = _normalize_secret_name(value)
    return bool(
        _SECRET_FLAG.fullmatch(normalized) or _SECRET_NAME_PART.search(normalized)
    )


def _sanitize_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://", value)
        return f"{scheme.group(1)}://<redacted-url>" if scheme else None
    if not parsed.scheme or not parsed.netloc:
        return None
    try:
        port_number = parsed.port
        hostname = parsed.hostname or ""
    except ValueError:
        return f"{parsed.scheme}://<redacted-url>"
    host = hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{port_number}" if port_number else ""
    path = parsed.path
    hostname = (parsed.hostname or "").casefold()
    if hostname == "hooks.slack.com" and path.startswith("/services/"):
        path = "/services/<redacted>"
    elif hostname == "api.telegram.org" and re.match(r"^/bot[^/]+", path):
        path = re.sub(r"^/bot[^/]+", "/bot<redacted>", path)
    elif re.match(r"^/(?:api/)?webhooks?/[^/]+/[^/]+", path, re.IGNORECASE):
        prefix = path.rsplit("/", 2)[0]
        path = prefix + "/<redacted>"
    return urlunsplit((parsed.scheme, host + port, path, "", ""))


def _redact_embedded_url(match: re.Match[str]) -> str:
    value = match.group(0)
    trailing = ""
    while value and value[-1] in ".,;!?)]}":
        trailing = value[-1] + trailing
        value = value[:-1]
    return (_sanitize_url(value) or value) + trailing


def redact_text(value: str) -> str:
    redacted = _PRIVATE_KEY.sub("<redacted private key>", value)
    redacted = _SENSITIVE_HEADER.sub(r"\1<redacted>", redacted)
    redacted = _EMBEDDED_SECRET.sub(r"\1<redacted>", redacted)
    redacted = _EMBEDDED_URL.sub(_redact_embedded_url, redacted)
    return _JWT.sub("<redacted token>", redacted)


def redact_argument(value: str) -> str:
    assignment = _ASSIGNMENT.match(value)
    if assignment:
        name, assigned = assignment.groups()
        if _is_secret_name(name):
            return f"{name}=<redacted>"
        return f"{name}={redact_text(assigned)}"
    sanitized_url = _sanitize_url(value)
    if sanitized_url is not None:
        return sanitized_url
    return redact_text(value)


def redact_command(command: object) -> list[str]:
    values = (
        []
        if command is None
        else command
        if isinstance(command, (list, tuple))
        else [command]
    )
    executable = Path(str(values[0])).name.casefold() if values else ""
    command_flags = _COMMAND_SECRET_FLAGS.get(executable, ())
    if executable == "docker" and any(str(value) == "login" for value in values[1:]):
        command_flags = ("--password", "-p")
    result: list[str] = []
    redact_next = False
    for raw in values:
        value = str(raw)
        if value == "--password-stdin":
            result.append(value)
            redact_next = False
            continue
        if redact_next:
            result.append("<redacted>")
            redact_next = False
            continue
        matched_flag = next(
            (
                flag
                for flag in command_flags
                if value == flag
                or value.startswith(flag + "=")
                or (len(flag) == 2 and value.startswith(flag) and len(value) > 2)
            ),
            "",
        )
        if matched_flag and value != matched_flag:
            separator = "=" if value.startswith(matched_flag + "=") else ""
            result.append(f"{matched_flag}{separator}<redacted>")
            continue
        result.append(redact_argument(value))
        redact_next = _is_secret_name(value) or bool(matched_flag)
    return result


def redact_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return value
    if address.is_loopback or address.is_unspecified:
        return value
    return "<private-ip>" if address.is_private else "<remote-ip>"


def redact_snapshot(
    snapshot: dict[str, object], home: Path | None = None
) -> dict[str, object]:
    home_path = str((home or Path.home()).resolve(strict=False))

    def visit(value: object, key: str = "") -> object:
        if isinstance(value, dict):
            return {
                str(child_key): visit(child, str(child_key))
                for child_key, child in value.items()
                if child_key not in {"previewPath"}
            }
        if isinstance(value, list):
            if key in _COMMAND_LIST_KEYS:
                return redact_command(value)
            return [visit(child, key) for child in value]
        if isinstance(value, str):
            if key and _is_secret_name(key):
                return "<redacted>"
            redacted = value.replace(home_path, "~") if home_path else value
            if key in {
                "localAddress",
                "remoteAddress",
                "address",
                "gateway",
                "hostAddress",
            }:
                redacted = redact_ip(redacted)
            return redact_argument(redacted)
        return value

    return visit(snapshot)
