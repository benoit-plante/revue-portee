"""Detect secrets in text files (ENF-SEC-04).

Used by the test suite to guarantee that no versioned file under ``tests/`` (cassettes,
fixtures, test code) contains an API key, an authentication header, a non-fictitious
``api_key``/``email``/``mailto`` parameter or the real contact address. Findings report
the file, the line and the kind of leak, never the matched value.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

__all__ = ["Finding", "is_fictitious_email", "is_placeholder", "scan_file", "scan_text"]

# A value containing one of these markers is a deliberate placeholder.
_PLACEHOLDER_MARKERS = (
    "fake",
    "dummy",
    "redacted",
    "placeholder",
    "fictif",
    "fictive",
    "example",
    "xxxx",
    "***",
    "{",
    "$",
    "<",
)

# RFC 2606 / RFC 6761 reserved domains.
_RESERVED_DOMAINS = ("example.com", "example.org", "example.net", "localhost")
_RESERVED_TLDS = (".example", ".test", ".invalid", ".localhost")

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@(?P<domain>[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)")
_ANTHROPIC_KEY = re.compile(r"sk-ant-[A-Za-z0-9_\-]*")
_AUTH_HEADER = re.compile(
    r"(?i)\b(?:authorization|x-api-key|api-key)[\"']?\s*[:=]\s*(?:-\s+)?[\"']?"
    r"(?:(?:bearer|basic|token)\s+)?(?P<value>[^\s\"',;}\]]+)"
)
_QUERY_PARAM = re.compile(r"(?i)[?&;](?P<name>api_key|apikey|email|mailto)=(?P<value>[^&\s\"'#]*)")
# API key given as a quoted literal: `api_key="..."`, JSON `"api_key": "..."`, YAML.
_KEY_LITERAL = re.compile(
    r"(?i)(?<![?&;])\b(?P<name>api_key|apikey)[\"']?\s*[:=]\s*(?P<q>[\"'])(?P<value>[^\"'\n]*)(?P=q)"
)
# API key given bare on its own line: YAML `api_key: ...`, `.env`/INI `api_key=...`.
# Not applied to Python files, where `api_key=name` is code referring to a variable.
_KEY_BARE = re.compile(
    r"(?im)^\s*(?:-\s+)?[\"']?(?P<name>api_key|apikey)[\"']?\s*[:=]\s*"
    r"(?P<value>[^\s\"'#,()\[\]{}]+)\s*(?:#.*)?$"
)


@dataclass(frozen=True, slots=True)
class Finding:
    """A suspected secret. Deliberately carries no matched value."""

    path: str
    line: int
    kind: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}"


def is_placeholder(value: str) -> bool:
    """Return ``True`` if ``value`` is visibly fictitious."""
    lowered = value.lower()
    return not value or any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def is_fictitious_email(address: str) -> bool:
    """Return ``True`` if ``address`` uses a reserved (non-routable) domain."""
    domain = address.rpartition("@")[2].lower().rstrip(".")
    return domain in _RESERVED_DOMAINS or domain.endswith(_RESERVED_TLDS)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def scan_text(text: str, *, path: str = "<text>", forbidden: Iterable[str] = ()) -> list[Finding]:
    """Return the suspected secrets in ``text``.

    ``forbidden`` holds exact values (e.g. the real ``CONTACT_EMAIL``) that must never
    appear, whether or not they look like secrets.
    """
    findings: list[Finding] = []

    for match in _ANTHROPIC_KEY.finditer(text):
        if not is_placeholder(match.group()):
            findings.append(Finding(path, _line_of(text, match.start()), "Anthropic API key"))

    for match in _AUTH_HEADER.finditer(text):
        if not is_placeholder(match.group("value")):
            findings.append(Finding(path, _line_of(text, match.start()), "authentication header"))

    for match in _QUERY_PARAM.finditer(text):
        value = unquote(match.group("value"))
        name = match.group("name").lower()
        fictitious = is_placeholder(value) or ("@" in value and is_fictitious_email(value))
        if not fictitious:
            findings.append(
                Finding(path, _line_of(text, match.start()), f"non-fictitious {name} parameter")
            )

    key_patterns = [_KEY_LITERAL] if path.endswith(".py") else [_KEY_LITERAL, _KEY_BARE]
    for pattern in key_patterns:
        for match in pattern.finditer(text):
            if not is_placeholder(match.group("value")):
                name = match.group("name").lower()
                findings.append(
                    Finding(path, _line_of(text, match.start()), f"non-fictitious {name} value")
                )

    decoded = unquote(text)  # catches URL-encoded addresses (%40)
    for match in _EMAIL.finditer(decoded):
        if not is_fictitious_email(match.group()) and not is_placeholder(match.group()):
            findings.append(Finding(path, _line_of(decoded, match.start()), "real email address"))

    for value in forbidden:
        if value and value in text:
            findings.append(
                Finding(path, _line_of(text, text.index(value)), "configured secret value")
            )

    return findings


def scan_file(
    path: Path, *, forbidden: Iterable[str] = (), display: str | None = None
) -> list[Finding]:
    """Scan one file; binary content is decoded leniently."""
    text = path.read_bytes().decode("utf-8", errors="replace")
    return scan_text(text, path=display or str(path), forbidden=forbidden)
