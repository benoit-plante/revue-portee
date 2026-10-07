"""Integration checks: run only on explicit request (`uv run pytest -m integration`)."""

import pytest

from revue_portee.config.secrets import SecretName, get_secret

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("name", list(SecretName))
def test_required_secret_is_configured(name: SecretName) -> None:
    # Raises MissingSecretError (name only, never a value) if the variable is absent.
    assert get_secret(name).get_secret_value()
