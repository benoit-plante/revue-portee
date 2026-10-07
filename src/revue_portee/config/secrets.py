"""Single access point to sensitive environment variables (ENF-SEC-01, ENF-SEC-02).

No other module may read ``REVUE_PORTEE_ANTHROPIC_KEY``/``ANTHROPIC_API_KEY``,
``OPENALEX_API_KEY`` or ``CONTACT_EMAIL`` from the environment. Values are returned as
:class:`pydantic.SecretStr`, whose ``repr`` and ``str`` are masked, and every loaded
value is registered so that
:class:`SecretRedactingFilter` can mask it in log output (ENF-SEC-03).

Error messages are user-facing and therefore in French; they name the missing variable
but never contain a value.
"""

import logging
import os
import re
import threading
from collections.abc import Mapping
from enum import StrEnum

from pydantic import SecretStr

__all__ = [
    "MASK",
    "MissingSecretError",
    "SecretName",
    "SecretRedactingFilter",
    "configured_secrets",
    "forget_loaded_secrets",
    "get_optional_secret",
    "get_secret",
    "install_secret_redaction",
    "redact",
    "redact_record",
]

MASK = "***"


class SecretName(StrEnum):
    """Sensitive values known to the application."""

    ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
    OPENALEX_API_KEY = "OPENALEX_API_KEY"
    CONTACT_EMAIL = "CONTACT_EMAIL"

    @property
    def env_vars(self) -> tuple[str, ...]:
        """Environment variables holding the value, in priority order."""
        return _ENV_VARS.get(self, (self.value,))

    @property
    def required(self) -> bool:
        """Whether the application cannot work without this value."""
        return self not in _OPTIONAL


# The project-specific name comes first: in Claude Code sessions, ANTHROPIC_API_KEY may
# be reserved for the session's own authentication.
_ENV_VARS: dict[SecretName, tuple[str, ...]] = {
    SecretName.ANTHROPIC_API_KEY: ("REVUE_PORTEE_ANTHROPIC_KEY", "ANTHROPIC_API_KEY"),
}

# Optional: in the cloud environment the network proxy injects the OpenAlex key into
# requests to api.openalex.org, so connectors send the key only when it is configured.
_OPTIONAL: frozenset[SecretName] = frozenset({SecretName.OPENALEX_API_KEY})


# User-facing descriptions (French interface).
_DESCRIPTIONS: dict[SecretName, str] = {
    SecretName.ANTHROPIC_API_KEY: "clé d'API Anthropic, utilisée par le réviseur IA",
    SecretName.OPENALEX_API_KEY: (
        "clé d'API OpenAlex, exigée par OpenAlex depuis février 2026 "
        "sauf si un mandataire réseau l'ajoute aux requêtes"
    ),
    SecretName.CONTACT_EMAIL: "adresse de contact transmise aux API bibliographiques",
}


class MissingSecretError(RuntimeError):
    """Raised when a required sensitive environment variable is absent or empty."""

    def __init__(self, name: SecretName) -> None:
        self.name = name
        super().__init__(
            f"Variable d'environnement manquante : {' ou '.join(name.env_vars)} "
            f"({_DESCRIPTIONS[name]}). "
            "Définissez-la dans les réglages de l'environnement, puis relancez la commande."
        )


_registry_lock = threading.Lock()
_loaded_values: set[str] = set()


def _register(value: str) -> None:
    with _registry_lock:
        _loaded_values.add(value)


def _loaded_snapshot() -> list[str]:
    with _registry_lock:
        # Longest first, so that a value containing another one is masked whole.
        return sorted(_loaded_values, key=len, reverse=True)


def forget_loaded_secrets() -> None:
    """Clear the registry of loaded values (for tests)."""
    with _registry_lock:
        _loaded_values.clear()


def configured_secrets(
    name: SecretName, *, environ: Mapping[str, str] | None = None
) -> list[SecretStr]:
    """Every non-blank value of the variables of ``name``, in priority order.

    All of them are registered for log redaction, not only the one that is used.
    ``environ`` defaults to :data:`os.environ`; tests pass a mapping instead.
    """
    source = os.environ if environ is None else environ
    secrets: list[SecretStr] = []
    for var in name.env_vars:
        raw = source.get(var, "").strip()
        if raw:
            _register(raw)
            secrets.append(SecretStr(raw))
    return secrets


def get_optional_secret(
    name: SecretName, *, environ: Mapping[str, str] | None = None
) -> SecretStr | None:
    """Return the secret, or ``None`` if none of its variables is set (blank counts as unset).

    The first non-blank variable of :attr:`SecretName.env_vars` wins.
    """
    secrets = configured_secrets(name, environ=environ)
    return secrets[0] if secrets else None


def get_secret(name: SecretName, *, environ: Mapping[str, str] | None = None) -> SecretStr:
    """Return the secret or raise :class:`MissingSecretError` with a French message."""
    secret = get_optional_secret(name, environ=environ)
    if secret is None:
        raise MissingSecretError(name)
    return secret


# Known key-like patterns, masked even when the value was never loaded.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Anthropic API keys.
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),
    # Authentication headers, in "Name: value", "name=value" or JSON/dict form.
    re.compile(
        r"(?i)(?P<keep>\b(?:authorization|x-api-key|api-key)[\"']?\s*[:=]\s*[\"']?"
        r"(?:(?:bearer|basic|token)\s+)?)[^\s\"',;}]+"
    ),
    # API keys as key=value, JSON/dict or YAML (e.g. an OpenAlex key injected by a proxy).
    re.compile(r"(?i)(?P<keep>\b(?:api_key|apikey)[\"']?\s*[:=]\s*[\"']?)[^\s\"',;}&#]+"),
    # Query-string credentials and contact parameters.
    re.compile(r"(?i)(?P<keep>[?&;](?:api_key|apikey|email|mailto)=)[^&\s\"'#]+"),
)


def _mask_loaded(text: str) -> str:
    for value in _loaded_snapshot():
        text = text.replace(value, MASK)
    return text


def redact(text: str) -> str:
    """Mask every loaded secret value and every known key pattern in ``text``."""
    text = _mask_loaded(text)
    for pattern in _PATTERNS:
        text = pattern.sub(lambda m: (m.groupdict().get("keep") or "") + MASK, text)
    return text


_exception_formatter = logging.Formatter()


def _redact_arg(arg: object) -> object:
    """Keep an argument as is unless its text holds a secret (then return masked text)."""
    try:
        text = str(arg)
    except Exception:  # an unprintable argument cannot leak through formatting either
        return arg
    redacted = redact(text)
    return arg if redacted == text else redacted


def redact_record(record: logging.LogRecord) -> None:
    """Mask secrets in ``record`` in place; never raises.

    The structure of ``msg`` and ``args`` is kept whenever possible, because some
    formatters (e.g. uvicorn's access log) read ``record.args`` directly. Exception
    and stack texts are rendered now so that every handler receives the masked text.
    """
    try:
        if isinstance(record.msg, str):
            # Loaded values only: key patterns would swallow placeholders ("api_key=%s").
            record.msg = _mask_loaded(record.msg)
        if isinstance(record.args, Mapping):
            record.args = {key: _redact_arg(value) for key, value in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(_redact_arg(value) for value in record.args)
        try:
            message = record.getMessage()
        except Exception:  # malformed call: logging reports it later, at emit time
            message = None
        if message is not None and redact(message) != message:
            # A secret only appears once template and arguments are combined.
            record.msg = redact(message)
            record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = _exception_formatter.formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
    except Exception:  # redaction must never break the caller's logging
        record.msg = "[message de journal masqué : échec du masquage des secrets]"
        record.args = None
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None


class SecretRedactingFilter(logging.Filter):
    """Logging filter that masks secrets in messages, exceptions and stack traces.

    Records are already masked at creation once :func:`install_secret_redaction` has
    run; the filter is a second line of defence for handlers that receive records
    built elsewhere (e.g. ``logging.makeLogRecord``).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        redact_record(record)
        return True


def _install_record_factory() -> None:
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_revue_portee_redacting", False):
        return

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        redact_record(record)
        return record

    factory._revue_portee_redacting = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


def install_secret_redaction(handler: logging.Handler | None = None) -> SecretRedactingFilter:
    """Mask secrets in every log record, whatever handler later receives it.

    Installs a record factory (records are masked when created, so handlers added
    later, such as uvicorn's, are covered) and attaches a :class:`SecretRedactingFilter`
    to ``handler``, or to every current root handler. Idempotent.
    """
    _install_record_factory()
    handlers = [handler] if handler is not None else list(logging.getLogger().handlers)
    redacting = SecretRedactingFilter()
    for target in handlers:
        if not any(isinstance(f, SecretRedactingFilter) for f in target.filters):
            target.addFilter(redacting)
    return redacting
