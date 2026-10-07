"""A fake task run end to end through the provider-agnostic layer (jalon 0)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import ValidationError

from revue_portee.ai import (
    ModelProvider,
    PromptRef,
    TaskInput,
    TaskOutput,
    TaskSpec,
    UnsupportedTaskError,
    run_task,
)
from revue_portee.ai.providers import FakeProvider

# Model names come from configuration; tests use obviously fictitious ones.
CONFIGURED_MODEL = "fake-model"
RETURNED_MODEL = "fake-model-2026-10-07"
FIXED_NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


class TitleInput(TaskInput):
    title: str


class TitleVerdict(TaskOutput):
    decision: Literal["include", "exclude", "uncertain"]
    rationale: str


TOY_TASK = TaskSpec[TitleInput, TitleVerdict](
    name="toy_title_screen",
    version="0.1",
    input_model=TitleInput,
    output_model=TitleVerdict,
    prompt=PromptRef(template_id="toy_title_screen", version="1"),
)


def keyword_responder(item: TaskInput) -> dict[str, str]:
    assert isinstance(item, TitleInput)
    if "parent" in item.title.lower():
        return {"decision": "include", "rationale": "Mentions parenting."}
    return {"decision": "uncertain", "rationale": "No parenting term."}


def make_provider(**kwargs: object) -> FakeProvider:
    return FakeProvider(
        model=CONFIGURED_MODEL,
        model_returned=RETURNED_MODEL,
        responder=keyword_responder,
        confidence=0.8,
        clock=lambda: FIXED_NOW,
        **kwargs,  # type: ignore[arg-type]
    )


def test_fake_provider_satisfies_protocol() -> None:
    assert isinstance(make_provider(), ModelProvider)


def test_fake_task_end_to_end() -> None:
    provider = make_provider()
    inputs = [
        TitleInput(item_id="ref-1", title="Parenting programmes and child anxiety"),
        TitleInput(item_id="ref-2", title="Soil erosion in alpine meadows"),
    ]

    estimate = provider.estimate_cost(TOY_TASK, inputs)
    assert estimate.amount == Decimal(0)
    assert estimate.input_tokens > 0

    results = run_task(provider, TOY_TASK, inputs)

    assert [r.item_id for r in results] == ["ref-1", "ref-2"]
    assert [r.output.decision for r in results] == ["include", "uncertain"]
    assert all(isinstance(r.output, TitleVerdict) for r in results)
    assert all(r.raw_confidence == 0.8 for r in results)

    call = results[0].call
    assert call.provider == "fake"
    assert call.model_requested == CONFIGURED_MODEL
    assert call.model_returned == RETURNED_MODEL
    assert call.prompt_template_id == "toy_title_screen"
    assert call.prompt_template_version == "1"
    assert len(call.prompt_sha256) == 64
    assert call.created_at == FIXED_NOW
    assert call.created_at.utcoffset() is not None
    assert results[0].call.prompt_sha256 != results[1].call.prompt_sha256
    assert provider.calls == [r.call for r in results]

    # Serialization keeps the concrete output fields.
    assert results[0].model_dump()["output"] == {
        "decision": "include",
        "rationale": "Mentions parenting.",
    }


def test_run_is_deterministic() -> None:
    inputs = [TitleInput(item_id="ref-1", title="Parent training")]
    first = run_task(make_provider(), TOY_TASK, inputs)
    second = run_task(make_provider(), TOY_TASK, inputs)
    assert first == second


def test_invalid_output_is_rejected() -> None:
    provider = FakeProvider(model=CONFIGURED_MODEL, responder=lambda _: {"decision": "maybe"})
    with pytest.raises(ValidationError):
        run_task(provider, TOY_TASK, [TitleInput(item_id="ref-1", title="x")])


def test_unsupported_task_is_refused() -> None:
    provider = make_provider(supported_tasks={"another_task"})
    assert not provider.supports(TOY_TASK)
    with pytest.raises(UnsupportedTaskError, match="toy_title_screen"):
        run_task(provider, TOY_TASK, [TitleInput(item_id="ref-1", title="x")])


def test_task_spec_checks_schema_types() -> None:
    with pytest.raises(ValidationError):
        TaskSpec[TitleInput, TitleVerdict](
            name="bad",
            version="1",
            input_model=TitleVerdict,  # type: ignore[arg-type]
            output_model=TitleVerdict,
            prompt=PromptRef(template_id="bad", version="1"),
        )
