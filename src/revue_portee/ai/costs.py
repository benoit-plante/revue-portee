"""Cost estimates and actual costs of model calls (ENF-COU-01, ENF-COU-03, ENF-COU-05).

Prices come from the dated file ``resources/model_prices.yaml``. Before a call, the
number of input tokens is estimated from the rendered prompt (about four characters
per token, rounded up: a deliberate over-estimate for French text), the instructions
being priced as written to the prompt cache, and the output from the task
configuration; after the call, the actual cost is computed from the
token counts returned by the provider.
"""

import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field

from revue_portee.ai.base import CostEstimate
from revue_portee.i18n import gettext as _

__all__ = [
    "ModelPrice",
    "PriceTable",
    "UnknownPriceError",
    "call_cost",
    "estimate",
    "estimate_tokens",
]

CHARS_PER_TOKEN = 4
_CENT_FRACTION = Decimal("0.000001")


class ModelPrice(BaseModel):
    """Prices per ``per_tokens`` tokens."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input: Decimal = Field(ge=0)
    output: Decimal = Field(ge=0)
    cache_write: Decimal = Field(ge=0)
    cache_read: Decimal = Field(ge=0)


class UnknownPriceError(LookupError):
    def __init__(self, provider: str, model: str) -> None:
        super().__init__(
            _(
                "No price is known for the model “{model}” of “{provider}”: add it to "
                "resources/model_prices.yaml before any call."
            ).format(model=model, provider=provider)
        )


class PriceTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: date
    source: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    per_tokens: int = Field(gt=0)
    providers: dict[str, dict[str, ModelPrice]]

    def price(self, provider: str, model: str) -> ModelPrice:
        found = self.providers.get(provider, {}).get(model)
        if found is None:
            raise UnknownPriceError(provider, model)
        return found


def estimate_tokens(text: str) -> int:
    """Rough token count of ``text`` (never zero for non-empty text)."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _amount(tokens: int, unit_price: Decimal, per_tokens: int) -> Decimal:
    return Decimal(tokens) * unit_price / Decimal(per_tokens)


def _rounded(amount: Decimal) -> Decimal:
    return amount.quantize(_CENT_FRACTION, rounding=ROUND_HALF_UP)


def estimate(
    table: PriceTable,
    provider: str,
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cacheable_tokens: int = 0,
) -> CostEstimate:
    """Cost before a call, in the most expensive case for the model asked for.

    ``cacheable_tokens`` (part of ``input_tokens``) are the instructions sent with a
    cache marker: they are priced as written to the cache, the dearer of the two prices,
    and no cache read discount is assumed. A server-side fallback to another model is
    priced at that model's rates once the call is made.
    """
    if not 0 <= cacheable_tokens <= input_tokens:
        raise ValueError("cacheable tokens are part of the input tokens")
    price = table.price(provider, model)
    per = table.per_tokens
    amount = (
        _amount(input_tokens - cacheable_tokens, price.input, per)
        + _amount(cacheable_tokens, max(price.cache_write, price.input), per)
        + _amount(output_tokens, price.output, per)
    )
    return CostEstimate(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        amount=_rounded(amount),
        currency=table.currency,
    )


def call_cost(
    table: PriceTable,
    provider: str,
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> Decimal:
    """Cost of a completed call. ``input_tokens`` excludes the cached tokens, as in the
    usage reported by the Anthropic API."""
    price = table.price(provider, model)
    per = table.per_tokens
    return _rounded(
        _amount(input_tokens, price.input, per)
        + _amount(output_tokens, price.output, per)
        + _amount(cache_read_tokens, price.cache_read, per)
        + _amount(cache_write_tokens, price.cache_write, per)
    )
