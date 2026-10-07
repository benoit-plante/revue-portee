"""AnthropicProvider with a stand-in SDK client: no network, no key."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from revue_portee.ai.base import PromptRef, ProviderCallError, TaskSpec, UnsupportedTaskError
from revue_portee.ai.costs import ModelPrice, PriceTable, UnknownPriceError
from revue_portee.ai.prompts import load_template
from revue_portee.ai.providers import UnknownProviderError, build_provider
from revue_portee.ai.providers.anthropic import (
    AnthropicProvider,
    UnsupportedParameterError,
    output_schema,
)
from revue_portee.ai.settings import AITaskConfig, TaskStatus
from revue_portee.ai.tasks import (
    QUALIFY_CRITERION_CHANGE,
    SUGGEST_PCC,
    CriterionSnapshot,
    QualifyChangeInput,
    QualifyChangeOutput,
    SuggestPccInput,
)

MODEL = "acme-large"
FALLBACK_MODEL = "acme-medium"
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
PRICES = PriceTable(
    as_of=date(2026, 10, 6),
    source="test",
    currency="USD",
    per_tokens=1_000_000,
    providers={
        "anthropic": {
            MODEL: ModelPrice(
                input=Decimal("4"),
                output=Decimal("20"),
                cache_write=Decimal("5"),
                cache_read=Decimal("0.2"),
            ),
            FALLBACK_MODEL: ModelPrice(
                input=Decimal("2"),
                output=Decimal("10"),
                cache_write=Decimal("2.5"),
                cache_read=Decimal("0.2"),
            ),
        }
    },
)
QUALIFY_INPUT = QualifyChangeInput(
    item_id="P1",
    language="fr",
    code="P1",
    pcc_element="population",
    before=CriterionSnapshot(kind="inclusion", text="Parents d'enfants de 0 à 12 ans"),
    after=CriterionSnapshot(kind="inclusion", text="Parents d'enfants de 0 à 17 ans"),
)


@dataclass
class Block:
    type: str
    text: str = ""


@dataclass
class Usage:
    input_tokens: int = 1_000
    output_tokens: int = 500
    cache_read_input_tokens: int = 10_000
    cache_creation_input_tokens: int = 2_000


@dataclass
class Message:
    content: list[Block]
    model: str = MODEL
    stop_reason: str | None = "end_turn"
    id: str = "msg_test"
    usage: Usage = field(default_factory=Usage)
    _request_id: str | None = "req_test"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "model": self.model,
            "stop_reason": self.stop_reason,
            "content": [{"type": b.type, "text": b.text} for b in self.content],
        }


class Endpoint:
    def __init__(self, replies: Iterator[Message | Exception]) -> None:
        self.requests: list[dict[str, Any]] = []
        self._replies = replies

    def create(self, **request: Any) -> Message:  # noqa: ANN401 - stands for the SDK
        self.requests.append(request)
        reply = next(self._replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


class Client:
    def __init__(self, *replies: Message | Exception) -> None:
        endpoint = Endpoint(iter(replies))
        self.messages = endpoint
        self.beta = type("Beta", (), {"messages": endpoint})()


def provider(client: Client, **params: Any) -> tuple[AnthropicProvider, list[str]]:  # noqa: ANN401
    keys: list[str] = []

    def api_key() -> SecretStr:
        keys.append("read")
        return SecretStr("DUMMY")

    return (
        AnthropicProvider(
            model=MODEL,
            params=params or {"max_tokens": 4000, "effort": "medium"},
            prices=PRICES,
            expected_output_tokens=1_500,
            clock=lambda: NOW,
            api_key=api_key,
            client_factory=lambda _key: client,
        ),
        keys,
    )


def qualification_json(change: str = "broadening") -> str:
    return (
        '{"change_type": "' + change + '", "confidence": 0.9, '
        '"rationale": "La tranche d\'âge est élargie."}'
    )


def test_successful_call_is_fully_recorded() -> None:
    client = Client(Message(content=[Block("thinking"), Block("text", qualification_json())]))
    tested, keys = provider(client)
    (result,) = list(tested.run(QUALIFY_CRITERION_CHANGE, [QUALIFY_INPUT]))
    assert result.item_id == "P1"
    assert isinstance(result.output, QualifyChangeOutput)
    assert (result.output.change_type, result.output.confidence) == ("broadening", 0.9)
    call = result.call
    assert call.provider == "anthropic"
    assert (call.model_requested, call.model_returned) == (MODEL, MODEL)
    assert call.provider_request_id == "req_test"
    assert (call.prompt_template_id, call.prompt_template_version) == (
        "qualify_criterion_change",
        "1",
    )
    prompt = load_template("qualify_criterion_change").render(QUALIFY_INPUT)
    assert call.prompt_sha256 == prompt.sha256
    assert (call.input_tokens, call.output_tokens) == (1_000, 500)
    assert (call.cache_read_tokens, call.cache_write_tokens) == (10_000, 2_000)
    # Same case as test_costs: 1 000 * 4 + 500 * 20 + 10 000 * 0.2 + 2 000 * 5 = 26 000 $/M.
    assert call.cost_estimate == Decimal("0.026000")
    assert call.status == "ok"
    assert call.params == {"max_tokens": 4000, "output_config": {"effort": "medium"}}
    assert call.created_at == NOW
    assert result.raw_response == Message(content=[]).to_dict() | {
        "content": [
            {"type": "thinking", "text": ""},
            {"type": "text", "text": qualification_json()},
        ]
    }
    assert keys == ["read"]


def test_request_has_cached_instructions_and_a_strict_schema() -> None:
    client = Client(Message(content=[Block("text", qualification_json())]))
    tested, _keys = provider(client)
    list(tested.run(QUALIFY_CRITERION_CHANGE, [QUALIFY_INPUT]))
    (request,) = client.messages.requests
    prompt = load_template("qualify_criterion_change").render(QUALIFY_INPUT)
    assert request["model"] == MODEL
    assert request["max_tokens"] == 4000
    assert request["system"] == [
        {"type": "text", "text": prompt.system, "cache_control": {"type": "ephemeral"}}
    ]
    assert request["messages"] == [{"role": "user", "content": prompt.user}]
    assert request["output_config"] == {
        "effort": "medium",
        "format": {"type": "json_schema", "schema": output_schema(QualifyChangeOutput)},
    }
    assert "betas" not in request


def test_fallbacks_use_the_beta_endpoint_and_the_answering_model_is_priced() -> None:
    reply = Message(content=[Block("text", qualification_json())], model=FALLBACK_MODEL)
    client = Client(reply)
    tested, _keys = provider(client, max_tokens=4000, fallbacks="default")
    (result,) = list(tested.run(QUALIFY_CRITERION_CHANGE, [QUALIFY_INPUT]))
    (request,) = client.beta.messages.requests
    assert request["fallbacks"] == "default"
    assert request["betas"] == ["server-side-fallback-2026-07-01"]
    assert result.call.model_returned == FALLBACK_MODEL
    # 1 000 * 2 + 500 * 10 + 10 000 * 0.2 + 2 000 * 2.5 = 14 000 $/M.
    assert result.call.cost_estimate == Decimal("0.014000")


def test_output_schema_has_only_supported_keywords() -> None:
    schema = output_schema(QualifyChangeOutput)
    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert properties["confidence"] == {"title": "Confidence", "type": "number"}
    text = str(output_schema(SUGGEST_PCC.output_model))
    for keyword in ("minLength", "maxItems", "maximum", "pattern", "default"):
        assert keyword not in text


@pytest.mark.parametrize(
    ("reply", "code", "message"),
    [
        (Message(content=[], stop_reason="refusal"), "refusal", "a refusé de répondre"),
        (
            Message(content=[Block("text", '{"change')], stop_reason="max_tokens"),
            "max_tokens",
            "tronquée",
        ),
        (
            Message(content=[Block("text", qualification_json("other"))]),
            "invalid_output",
            "format attendu",
        ),
    ],
)
def test_unusable_answers_are_recorded_as_failed_calls(
    reply: Message, code: str, message: str
) -> None:
    tested, _keys = provider(Client(reply))
    with pytest.raises(ProviderCallError, match=message) as raised:
        list(tested.run(QUALIFY_CRITERION_CHANGE, [QUALIFY_INPUT]))
    assert raised.value.item_id == "P1"
    assert (raised.value.call.status, raised.value.call.error_code) == ("error", code)
    assert raised.value.call.input_tokens == 1_000
    assert raised.value.raw_response == reply.to_dict()


REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
ERROR_HEADERS = {"request-id": "req_error"}


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (anthropic.APIConnectionError(request=REQUEST), "api.anthropic.com doit être autorisé"),
        (
            anthropic.AuthenticationError(
                "invalid",
                response=httpx2.Response(401, request=REQUEST, headers=ERROR_HEADERS),
                body=None,
            ),
            "REVUE_PORTEE_ANTHROPIC_KEY",
        ),
        (
            anthropic.RateLimitError(
                "limit",
                response=httpx2.Response(429, request=REQUEST, headers=ERROR_HEADERS),
                body=None,
            ),
            "réessayez plus tard",
        ),
        (
            anthropic.InternalServerError(
                "boom",
                response=httpx2.Response(500, request=REQUEST, headers=ERROR_HEADERS),
                body=None,
            ),
            "InternalServerError",
        ),
    ],
)
def test_api_errors_are_recorded_without_tokens(error: Exception, message: str) -> None:
    tested, _keys = provider(Client(error))
    with pytest.raises(ProviderCallError, match=message) as raised:
        list(tested.run(QUALIFY_CRITERION_CHANGE, [QUALIFY_INPUT]))
    call = raised.value.call
    assert (call.status, call.error_code) == ("error", type(error).__name__)
    assert (call.input_tokens, call.output_tokens, call.cost_estimate) == (0, 0, Decimal(0))
    assert call.model_requested == MODEL
    assert call.model_returned is None  # the API returned no model
    expected_id = None if isinstance(error, anthropic.APIConnectionError) else "req_error"
    assert call.provider_request_id == expected_id
    assert raised.value.raw_response is None


def test_estimate_needs_no_key_and_counts_the_schema() -> None:
    tested, keys = provider(Client())
    item = SuggestPccInput(item_id="f1", language="fr", question="Quelles interventions ?")
    estimate = tested.estimate_cost(SUGGEST_PCC, [item, item])
    assert keys == []
    prompt = load_template("suggest_pcc").render(item)
    schema = str(output_schema(SUGGEST_PCC.output_model))
    system = -(-len(prompt.system) // 4)
    other = -(-len(prompt.user + schema) // 4)
    assert estimate.input_tokens == 2 * (system + other)
    assert estimate.output_tokens == 3_000
    # Instructions at the cache write price (5), the rest at the input price (4).
    expected = Decimal(2 * system) * 5 + Decimal(2 * other) * 4 + Decimal(3_000) * 20
    assert estimate.amount == (expected / Decimal(1_000_000)).quantize(Decimal("0.000001"))


def test_unknown_price_blocks_the_estimate() -> None:
    tested = AnthropicProvider(
        model="acme-unknown", params={}, prices=PRICES, expected_output_tokens=10
    )
    item = SuggestPccInput(item_id="f1", language="fr", question="Q ?")
    with pytest.raises(UnknownPriceError):
        tested.estimate_cost(SUGGEST_PCC, [item])


def test_tasks_without_template_are_not_supported() -> None:
    tested, _keys = provider(Client())
    other = TaskSpec(
        name="other",
        version="1",
        input_model=QualifyChangeInput,
        output_model=QualifyChangeOutput,
        prompt=PromptRef(template_id="does_not_exist", version="1"),
    )
    stale = other.model_copy(update={"prompt": PromptRef(template_id="suggest_pcc", version="0")})
    assert tested.supports(SUGGEST_PCC)
    assert not tested.supports(other)
    assert not tested.supports(stale)
    with pytest.raises(UnsupportedTaskError):
        tested.run(other, [QUALIFY_INPUT])


def test_unsupported_parameters_are_refused() -> None:
    with pytest.raises(UnsupportedParameterError, match="temperature"):
        AnthropicProvider(
            model=MODEL, params={"temperature": 0}, prices=PRICES, expected_output_tokens=1
        )


def test_build_provider_from_configuration() -> None:
    config = AITaskConfig(status=TaskStatus.ENABLED, provider="anthropic", model=MODEL)
    assert isinstance(build_provider(config, prices=PRICES), AnthropicProvider)
    other = AITaskConfig(status=TaskStatus.ENABLED, provider="other", model=MODEL)
    with pytest.raises(UnknownProviderError, match="other"):
        build_provider(other, prices=PRICES)


def test_blank_text_is_an_invalid_output() -> None:
    blank = '{"change_type": "broadening", "confidence": 0.9, "rationale": "  "}'
    tested, _keys = provider(Client(Message(content=[Block("text", blank)])))
    # rationale may be empty, but suggestion texts may not: check both task schemas.
    (result,) = list(tested.run(QUALIFY_CRITERION_CHANGE, [QUALIFY_INPUT]))
    assert result.output.rationale == ""
    suggestion = '{"suggestions": [{"kind": "concept", "text": "  ", "rationale": "x"}]}'
    tested, _keys = provider(Client(Message(content=[Block("text", suggestion)])))
    item = SuggestPccInput(item_id="f1", language="fr", question="Q ?")
    with pytest.raises(ProviderCallError) as raised:
        list(tested.run(SUGGEST_PCC, [item]))
    assert raised.value.call.error_code == "invalid_output"


def test_field_names_survive_schema_cleaning() -> None:
    from revue_portee.ai.base import TaskOutput

    class Odd(TaskOutput):
        pattern: str
        default: int

    schema = output_schema(Odd)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == {"pattern", "default"}
    assert schema["required"] == ["pattern", "default"]
