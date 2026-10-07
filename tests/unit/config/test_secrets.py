import io
import logging
import secrets as token_source
from collections.abc import Iterator

import pytest
from pydantic import BaseModel, SecretStr

from revue_portee.config.secrets import (
    MASK,
    MissingSecretError,
    SecretName,
    SecretRedactingFilter,
    configured_secrets,
    get_optional_secret,
    get_secret,
    install_secret_redaction,
    redact,
    redact_record,
)


def make_fake_key() -> str:
    """A key-shaped random value, built at run time so that no file contains it."""
    return "sk-" + "ant-" + "api03-" + token_source.token_urlsafe(32)


@pytest.fixture
def capture() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    install_secret_redaction(handler)
    logger = logging.getLogger("revue_portee.tests.secrets")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)
    yield logger, stream
    logger.removeHandler(handler)


@pytest.mark.parametrize(
    ("name", "var"),
    [(name, var) for name in SecretName for var in name.env_vars],
)
def test_get_secret_returns_secret_str(name: SecretName, var: str) -> None:
    value = token_source.token_hex(16)
    secret = get_secret(name, environ={var: f"  {value}\n"})
    assert isinstance(secret, SecretStr)
    assert secret.get_secret_value() == value


def test_anthropic_key_variables_and_priority() -> None:
    name = SecretName.ANTHROPIC_API_KEY
    assert name.env_vars == ("REVUE_PORTEE_ANTHROPIC_KEY", "ANTHROPIC_API_KEY")
    project, generic = token_source.token_hex(16), token_source.token_hex(16)
    both = {"REVUE_PORTEE_ANTHROPIC_KEY": project, "ANTHROPIC_API_KEY": generic}
    assert get_secret(name, environ=both).get_secret_value() == project
    blank_first = {"REVUE_PORTEE_ANTHROPIC_KEY": "  ", "ANTHROPIC_API_KEY": generic}
    assert get_secret(name, environ=blank_first).get_secret_value() == generic


def test_missing_anthropic_key_names_both_variables() -> None:
    with pytest.raises(MissingSecretError) as excinfo:
        get_secret(SecretName.ANTHROPIC_API_KEY, environ={})
    assert "REVUE_PORTEE_ANTHROPIC_KEY ou ANTHROPIC_API_KEY" in str(excinfo.value)


def test_only_openalex_key_is_optional() -> None:
    assert not SecretName.OPENALEX_API_KEY.required
    assert SecretName.ANTHROPIC_API_KEY.required
    assert SecretName.CONTACT_EMAIL.required


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_secret_raises_clear_french_message(raw: str | None) -> None:
    environ = {} if raw is None else {"OPENALEX_API_KEY": raw}
    with pytest.raises(MissingSecretError) as excinfo:
        get_secret(SecretName.OPENALEX_API_KEY, environ=environ)
    message = str(excinfo.value)
    assert "Variable d'environnement manquante :" in message
    assert "OPENALEX_API_KEY" in message
    assert "réglages de l'environnement" in message
    assert excinfo.value.name is SecretName.OPENALEX_API_KEY


def test_optional_secret_is_none_when_absent() -> None:
    assert get_optional_secret(SecretName.CONTACT_EMAIL, environ={}) is None


def test_reads_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    value = make_fake_key()
    monkeypatch.delenv("REVUE_PORTEE_ANTHROPIC_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", value)
    assert get_secret(SecretName.ANTHROPIC_API_KEY).get_secret_value() == value


def test_secret_never_appears_in_repr_or_str() -> None:
    value = make_fake_key()
    secret = get_secret(SecretName.ANTHROPIC_API_KEY, environ={"ANTHROPIC_API_KEY": value})

    class Holder(BaseModel):
        key: SecretStr

    holder = Holder(key=secret)
    renderings = [
        repr(secret),
        str(secret),
        f"{secret}",
        f"{secret!r}",
        repr(holder),
        str(holder),
        holder.model_dump_json(),
        repr(holder.model_dump()),
    ]
    for rendering in renderings:
        assert value not in rendering


def test_missing_secret_error_repr_contains_no_value() -> None:
    value = make_fake_key()
    environ = {"REVUE_PORTEE_ANTHROPIC_KEY": value, "CONTACT_EMAIL": "  "}
    get_secret(SecretName.ANTHROPIC_API_KEY, environ=environ)
    with pytest.raises(MissingSecretError) as excinfo:
        get_secret(SecretName.CONTACT_EMAIL, environ=environ)
    assert value not in repr(excinfo.value)
    assert value not in str(excinfo.value)


def test_loaded_secret_is_masked_in_every_log_output(
    capture: tuple[logging.Logger, io.StringIO], caplog: pytest.LogCaptureFixture
) -> None:
    logger, stream = capture
    install_secret_redaction(caplog.handler)
    key = make_fake_key()
    email = f"{token_source.token_hex(6)}@example.org"
    environ = {"REVUE_PORTEE_ANTHROPIC_KEY": key, "CONTACT_EMAIL": email}
    raw_key = get_secret(SecretName.ANTHROPIC_API_KEY, environ=environ).get_secret_value()
    raw_email = get_secret(SecretName.CONTACT_EMAIL, environ=environ).get_secret_value()

    logger.addHandler(caplog.handler)
    try:
        logger.info("key=%s", raw_key)
        logger.warning(f"contact {raw_email} and key {raw_key}")
        logger.error("dict %(k)s", {"k": raw_key})
        try:
            raise ValueError(f"bad key {raw_key}")
        except ValueError:
            logger.exception("failure with %s", raw_email)
        logger.debug("stack", stack_info=True, extra={"unused": raw_key})
    finally:
        logger.removeHandler(caplog.handler)

    outputs = [stream.getvalue(), caplog.text, *(r.getMessage() for r in caplog.records)]
    for output in outputs:
        assert raw_key not in output
        assert raw_email not in output
    assert MASK in stream.getvalue()
    assert "ValueError: bad key ***" in stream.getvalue()


def test_known_patterns_are_masked_even_when_not_loaded() -> None:
    key = make_fake_key()
    token = token_source.token_urlsafe(24)
    header = "Author" + "ization"
    real_domain = "university" + ".ca"
    text = (
        f"key {key}; {header}: Bearer {token}; x-api-key={token}; "
        f"https://api.openalex.org/works?api_key={token}&mailto=someone%40{real_domain}"
    )
    redacted = redact(text)
    assert key not in redacted
    assert token not in redacted
    assert real_domain not in redacted
    assert f"{header}: Bearer {MASK}" in redacted
    assert "?api_key=***&mailto=***" in redacted


def test_install_is_idempotent() -> None:
    handler = logging.StreamHandler(io.StringIO())
    install_secret_redaction(handler)
    install_secret_redaction(handler)
    assert sum(isinstance(f, SecretRedactingFilter) for f in handler.filters) == 1


def make_record(msg: object, args: tuple[object, ...] | dict[str, object]) -> logging.LogRecord:
    return logging.LogRecord("x", logging.WARNING, __file__, 1, msg, args, None)


def test_malformed_record_keeps_masked_template() -> None:
    key = get_secret(
        SecretName.OPENALEX_API_KEY, environ={"OPENALEX_API_KEY": token_source.token_hex(20)}
    ).get_secret_value()
    record = make_record("%s %s " + key, ("only-one-argument",))
    assert SecretRedactingFilter().filter(record)
    assert key not in str(record.msg)


def test_every_fallback_variable_is_registered_for_redaction() -> None:
    project, generic = token_source.token_hex(16), token_source.token_hex(16)
    environ = {"REVUE_PORTEE_ANTHROPIC_KEY": project, "ANTHROPIC_API_KEY": generic}
    secrets = configured_secrets(SecretName.ANTHROPIC_API_KEY, environ=environ)
    assert [s.get_secret_value() for s in secrets] == [project, generic]
    get_secret(SecretName.ANTHROPIC_API_KEY, environ=environ)
    assert redact(f"{project} {generic}") == f"{MASK} {MASK}"


def test_unloaded_api_key_assignments_are_masked() -> None:
    token = token_source.token_hex(12)
    key = "api_" + "key"
    for text in (f"{key}={token}", f'{{"{key}": "{token}"}}', f"{key}: {token}"):
        redacted = redact(text)
        assert token not in redacted, text
        assert MASK in redacted


class Unprintable:
    def __str__(self) -> str:
        raise RuntimeError("boom")


@pytest.mark.parametrize(
    ("template", "args"),
    [
        ("%(k)s", ({"x": 1},)),  # KeyError at formatting
        ("%s %s", ("only-one",)),  # TypeError
        ("%d", ("not-a-number",)),  # TypeError
        ("value %s", (Unprintable(),)),  # __str__ raises
        (Unprintable(), ()),  # msg itself is unprintable
    ],
)
def test_redaction_never_raises(
    template: object, args: tuple[object, ...] | dict[str, object]
) -> None:
    # Before the fix, the filter let KeyError and other exceptions escape Handler.filter,
    # which logging does not guard, so a bad log call crashed the caller. Now logging
    # reports the problem itself, at emit time ("--- Logging error ---").
    record = make_record(template, args)
    assert SecretRedactingFilter().filter(record)
    redact_record(record)


def test_handler_added_after_install_receives_masked_records() -> None:
    install_secret_redaction()
    key = get_secret(
        SecretName.OPENALEX_API_KEY, environ={"OPENALEX_API_KEY": token_source.token_hex(20)}
    ).get_secret_value()
    stream = io.StringIO()
    late_handler = logging.StreamHandler(stream)  # e.g. uvicorn's, configured later
    logger = logging.getLogger("revue_portee.tests.late")
    logger.propagate = False
    logger.addHandler(late_handler)
    try:
        logger.warning("key=%s", key)
        try:
            raise ValueError(key)
        except ValueError:
            logger.exception("failure")
    finally:
        logger.removeHandler(late_handler)
    assert key not in stream.getvalue()
    assert MASK in stream.getvalue()


def test_record_structure_is_kept_when_no_secret() -> None:
    install_secret_redaction()
    record = logging.getLogger("revue_portee.tests.args").makeRecord(
        "x", logging.INFO, __file__, 1, '%s - "%s %s"', ("127.0.0.1", "GET", "/"), None
    )
    factory_record = logging.getLogRecordFactory()(
        "x", logging.INFO, __file__, 1, '%s - "%s %s"', ("127.0.0.1", "GET", "/"), None
    )
    # Formatters such as uvicorn's access log unpack record.args.
    assert factory_record.args == ("127.0.0.1", "GET", "/")
    assert record.getMessage() == '127.0.0.1 - "GET /"'


@pytest.mark.parametrize("template", ["api_" + "key=%s", "Author" + "ization: Bearer %s"])
def test_secret_completed_by_arguments_is_masked(template: str) -> None:
    token = token_source.token_hex(12)
    record = make_record(template, (token,))
    redact_record(record)
    message = record.getMessage()  # no formatting error: the placeholder was kept
    assert token not in message
    assert message.endswith(MASK)


def test_redaction_failure_masks_whole_record(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> list[str]:
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr("revue_portee.config.secrets._loaded_snapshot", broken)
    record = make_record("key %s", ("value",))
    redact_record(record)
    assert record.args is None
    assert "échec du masquage" in record.getMessage()
