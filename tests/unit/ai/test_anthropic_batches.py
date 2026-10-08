"""AnthropicProvider with the Message Batches API, through a stand-in SDK client."""

from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from revue_portee.ai.base import BatchError, BatchProvider, ProviderCallError, TaskResult
from revue_portee.ai.providers.anthropic import AnthropicProvider
from revue_portee.ai.tasks import QUALIFY_CRITERION_CHANGE, QualifyChangeInput

from .test_anthropic_provider import MODEL, NOW, PRICES, QUALIFY_INPUT, Block, Message

OK = '{"change_type": "broadening", "confidence": 0.9, "rationale": "Plus large."}'
PRICED = PRICES.model_copy(update={"batch_factor": {"anthropic": Decimal("0.5")}})


def item(item_id: str) -> QualifyChangeInput:
    return QUALIFY_INPUT.model_copy(update={"item_id": item_id})


@dataclass
class Batches:
    entries: list[Any] = field(default_factory=list)
    created: list[dict[str, Any]] = field(default_factory=list)
    status: str = "in_progress"
    error: Exception | None = None

    def create(self, **request: Any) -> SimpleNamespace:  # noqa: ANN401
        if self.error is not None:
            raise self.error
        self.created.append(request)
        return SimpleNamespace(id="msgbatch_test")

    def retrieve(self, batch_id: str) -> SimpleNamespace:
        counts = SimpleNamespace(processing=1, succeeded=2, errored=1, canceled=0, expired=1)
        return SimpleNamespace(id=batch_id, processing_status=self.status, request_counts=counts)

    def results(self, batch_id: str) -> list[Any]:
        return self.entries


def entry(custom_id: str, kind: str, message: Message | None = None) -> SimpleNamespace:
    result = SimpleNamespace(type=kind, message=message, error=SimpleNamespace(type="api_error"))
    return SimpleNamespace(custom_id=custom_id, result=result)


class Client:
    def __init__(self, batches: Batches) -> None:
        self.messages = SimpleNamespace(batches=batches)
        self.beta = SimpleNamespace(messages=SimpleNamespace(batches=batches))


def provider(batches: Batches, **params: Any) -> AnthropicProvider:  # noqa: ANN401
    return AnthropicProvider(
        model=MODEL,
        params=params or {"max_tokens": 4000, "effort": "low"},
        prices=PRICED,
        expected_output_tokens=1_500,
        clock=lambda: NOW,
        api_key=lambda: SecretStr("DUMMY"),
        client_factory=lambda _key: Client(batches),
    )


def test_batch_is_submitted_with_one_cached_request_per_item() -> None:
    batches = Batches()
    chosen = provider(batches)
    assert isinstance(chosen, BatchProvider)
    batch_id = chosen.submit_batch(QUALIFY_CRITERION_CHANGE, [item("P1"), item("C2")])
    assert batch_id == "msgbatch_test"
    (sent,) = batches.created
    assert [r["custom_id"] for r in sent["requests"]] == ["P1", "C2"]
    params = sent["requests"][0]["params"]
    assert params["model"] == MODEL
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert params["output_config"]["effort"] == "low"
    assert "betas" not in sent


def test_batch_estimate_is_half_the_call_estimate() -> None:
    chosen = provider(Batches())
    inputs = [item("P1"), item("C2")]
    call = chosen.estimate_cost(QUALIFY_CRITERION_CHANGE, inputs).amount
    batch = chosen.estimate_batch_cost(QUALIFY_CRITERION_CHANGE, inputs).amount
    assert batch == pytest.approx(call / 2, abs=Decimal("0.000001"))


def test_status_and_results_of_an_ended_batch() -> None:
    batches = Batches(
        status="ended",
        entries=[
            entry("P1", "succeeded", Message(content=[Block("text", OK)])),
            entry("C2", "succeeded", Message(content=[Block("text", "pas du JSON")])),
            entry("X1", "errored"),
            entry("X2", "expired"),
            entry("unknown", "succeeded", Message(content=[Block("text", OK)])),
        ],
    )
    chosen = provider(batches)
    status = chosen.batch_status("msgbatch_test")
    assert status.ended
    assert (status.succeeded, status.errored, status.expired) == (2, 1, 1)
    outcomes = list(
        chosen.batch_results(
            QUALIFY_CRITERION_CHANGE,
            "msgbatch_test",
            [item("P1"), item("C2"), item("X1"), item("X2")],
        )
    )
    assert len(outcomes) == 4  # the request nobody asked for is ignored
    ok, invalid, errored, expired = outcomes
    assert isinstance(ok, TaskResult)
    assert ok.call.batch_id == "msgbatch_test"
    # Usage 1 000 in, 500 out, 10 000 cache reads, 2 000 cache writes, at half price:
    # (1 000 * 4 + 500 * 20 + 10 000 * 0.2 + 2 000 * 5) / 1e6 / 2 = 0.013
    assert ok.call.cost_estimate == Decimal("0.013")
    assert isinstance(invalid, ProviderCallError)
    assert invalid.call.error_code == "invalid_output"
    assert invalid.raw_response is not None
    assert isinstance(errored, ProviderCallError)
    assert errored.call.error_code == "batch_api_error"
    assert errored.call.model_returned is None
    assert errored.call.cost_estimate == 0
    assert isinstance(expired, ProviderCallError)
    assert expired.call.error_code == "batch_expired"
    assert "24" in str(expired)


def test_fallbacks_go_through_the_beta_batches() -> None:
    batches = Batches()
    chosen = provider(batches, max_tokens=4000, fallbacks="default")
    chosen.submit_batch(QUALIFY_CRITERION_CHANGE, [item("P1")])
    (sent,) = batches.created
    assert sent["betas"]
    assert "betas" not in sent["requests"][0]["params"]


def test_api_errors_become_batch_errors() -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages/batches")
    failure = anthropic.APIConnectionError(request=request)
    chosen = provider(Batches(error=failure))
    with pytest.raises(BatchError, match=r"api\.anthropic\.com"):
        chosen.submit_batch(QUALIFY_CRITERION_CHANGE, [item("P1")])
