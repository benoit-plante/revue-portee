"""Integration checks: run only on explicit request (`uv run pytest -m integration`)."""

import pytest

from revue_portee.config.secrets import SecretName, get_optional_secret, get_secret

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("name", [name for name in SecretName if name.required])
def test_required_secret_is_configured(name: SecretName) -> None:
    # Raises MissingSecretError (variable names only, never a value) if absent.
    assert get_secret(name).get_secret_value()


@pytest.mark.parametrize("name", [name for name in SecretName if not name.required])
def test_optional_secret_is_reported(name: SecretName) -> None:
    if get_optional_secret(name) is None:
        pytest.skip(f"{' / '.join(name.env_vars)} absente (facultative)")
