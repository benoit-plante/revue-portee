"""Cost estimates and actual costs, checked on cases computed by hand."""

from datetime import date
from decimal import Decimal

import pytest

from revue_portee.ai.costs import (
    ModelPrice,
    PriceTable,
    UnknownPriceError,
    call_cost,
    estimate,
    estimate_tokens,
)
from revue_portee.resources import price_table

TABLE = PriceTable(
    as_of=date(2026, 10, 6),
    source="test",
    currency="USD",
    per_tokens=1_000_000,
    providers={
        "acme": {
            "model-a": ModelPrice(
                input=Decimal("4.00"),
                output=Decimal("20.00"),
                cache_write=Decimal("5.00"),
                cache_read=Decimal("0.20"),
            )
        }
    },
)


def test_estimate_tokens_rounds_up_four_characters_per_token() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
    assert estimate_tokens("é" * 400) == 100


def test_estimate_by_hand() -> None:
    # 2 500 input tokens * 4 $/M = 0.01 $; 3 000 output tokens * 20 $/M = 0.06 $.
    result = estimate(TABLE, "acme", "model-a", input_tokens=2_500, output_tokens=3_000)
    assert result.amount == Decimal("0.070000")
    assert (result.input_tokens, result.output_tokens, result.currency) == (2_500, 3_000, "USD")


def test_call_cost_by_hand_with_cache() -> None:
    # 1 000 * 4 + 500 * 20 + 10 000 * 0.20 + 2 000 * 5 = 4 000 + 10 000 + 2 000 + 10 000
    # = 26 000 $ per million tokens, i.e. 0.026 $.
    cost = call_cost(
        TABLE,
        "acme",
        "model-a",
        input_tokens=1_000,
        output_tokens=500,
        cache_read_tokens=10_000,
        cache_write_tokens=2_000,
    )
    assert cost == Decimal("0.026000")


def test_costs_are_rounded_to_a_millionth() -> None:
    # 1 output token = 0.00002 $; 1 cached token read = 0.0000002 $ -> rounds to 0.
    assert call_cost(TABLE, "acme", "model-a", input_tokens=0, output_tokens=1) == Decimal(
        "0.000020"
    )
    assert call_cost(
        TABLE, "acme", "model-a", input_tokens=0, output_tokens=0, cache_read_tokens=1
    ) == Decimal("0.000000")


def test_unknown_price_is_refused_in_french() -> None:
    with pytest.raises(UnknownPriceError, match="Aucun tarif n'est connu pour le modèle"):
        estimate(TABLE, "acme", "model-b", input_tokens=1, output_tokens=1)
    with pytest.raises(UnknownPriceError):
        TABLE.price("other", "model-a")


def test_price_file_is_dated_and_complete() -> None:
    table = price_table()
    assert table.as_of == date(2026, 10, 6)
    assert table.currency == "USD"
    for prices in table.providers.values():
        for price in prices.values():
            assert price.output >= price.input >= price.cache_read
            assert price.cache_write == price.input * Decimal("1.25")
