import secrets as token_source

import pytest

from revue_portee.config.secret_scan import is_fictitious_email, is_placeholder, scan_text

# Key-shaped strings are assembled at run time so that this file stays clean.
ANTHROPIC_PREFIX = "sk-" + "ant-"
AUTH = "Author" + "ization"
REAL_DOMAIN = "university" + ".ca"


def real_looking_token() -> str:
    return token_source.token_urlsafe(24).replace("-", "a").replace("_", "b")


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (f"key = '{ANTHROPIC_PREFIX}api03-{real_looking_token()}'", "Anthropic API key"),
        (f"{AUTH}: Bearer {real_looking_token()}", "authentication header"),
        (f'"x-api-key": "{real_looking_token()}"', "authentication header"),
        (f"    {AUTH}:\n    - {real_looking_token()}\n", "authentication header"),
        (f"uri: https://api.openalex.org/works?api_key={real_looking_token()}", "api_key"),
        (f"uri: https://api.crossref.org/works?mailto=jane%40{REAL_DOMAIN}", "mailto"),
        (f"uri: https://api.unpaywall.org/v2/x?email=jane@{REAL_DOMAIN}", "email"),
        (f"contact: jane.doe@{REAL_DOMAIN}", "real email address"),
    ],
)
def test_detects_secrets(text: str, kind: str) -> None:
    findings = scan_text(text, path="cassette.yaml")
    assert findings, text
    assert any(kind in finding.kind for finding in findings)


@pytest.mark.parametrize(
    "text",
    [
        f"key = '{ANTHROPIC_PREFIX}FAKE-for-tests'",
        f"{AUTH}: Bearer DUMMY",
        f"    {AUTH}:\n    - DUMMY\n",
        "uri: https://api.openalex.org/works?api_key=DUMMY&mailto=contact%40example.org",
        "uri: https://api.unpaywall.org/v2/x?email=contact@example.org",
        "author: someone@university.test",
        "api_key=SecretStr('x')",  # code, not a query parameter
    ],
)
def test_accepts_fictitious_values(text: str) -> None:
    assert scan_text(text) == []


def test_forbidden_value_is_reported_without_its_value() -> None:
    value = f"{real_looking_token()}@example.org"
    findings = scan_text(f"line one\nheaders: {value}\n", path="f.yaml", forbidden=[value])
    assert [(f.line, f.kind) for f in findings] == [(2, "configured secret value")]
    assert all(value not in str(finding) for finding in findings)


def test_findings_never_contain_matched_value() -> None:
    token = real_looking_token()
    findings = scan_text(f"{AUTH}: Bearer {token}", path="f.yaml")
    assert findings
    assert all(token not in str(finding) for finding in findings)


def test_helpers() -> None:
    assert is_placeholder("DUMMY")
    assert is_placeholder("")
    assert not is_placeholder(real_looking_token())
    assert is_fictitious_email("a@example.com")
    assert is_fictitious_email("a@mail.invalid")
    assert not is_fictitious_email(f"a@{REAL_DOMAIN}")
