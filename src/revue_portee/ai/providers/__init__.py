"""Model providers implementing the ModelProvider protocol."""

from collections.abc import Callable

from revue_portee.ai.base import ModelProvider
from revue_portee.ai.costs import PriceTable
from revue_portee.ai.providers.anthropic import PROVIDER_NAME as ANTHROPIC
from revue_portee.ai.providers.anthropic import AnthropicProvider
from revue_portee.ai.providers.fake import FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.i18n import gettext as _

__all__ = [
    "AnthropicProvider",
    "FakeProvider",
    "ProviderFactory",
    "UnknownProviderError",
    "build_provider",
]

type ProviderFactory = Callable[[AITaskConfig], ModelProvider]


class UnknownProviderError(LookupError):
    def __init__(self, provider: str) -> None:
        super().__init__(_("Unknown AI provider: {provider}.").format(provider=provider))


def build_provider(config: AITaskConfig, *, prices: PriceTable) -> ModelProvider:
    """Provider configured for one task (``config`` must be enabled)."""
    if config.provider == ANTHROPIC and config.model:
        return AnthropicProvider(
            model=config.model,
            params=config.params,
            prices=prices,
            expected_output_tokens=config.expected_output_tokens,
        )
    raise UnknownProviderError(str(config.provider))
