"""Claude through the official ``anthropic`` SDK (docs/03-architecture.md §6.3).

The model name and parameters come from the project configuration. Outputs are
constrained by the task's JSON schema (structured outputs) and validated again with
Pydantic. Each call yields a complete :class:`AICallRecord`: the exact model identifier
returned by the API, the request identifier, token counts (cache included), cost and
latency, plus the raw response for the project archive (ENF-TRA-01, ENF-TRA-03).

The API key is read only when a call is made (``config/secrets.py``), so that a cost
can be estimated without it.
"""

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, cast

import anthropic
from pydantic import BaseModel, JsonValue, SecretStr, ValidationError

from revue_portee.ai.base import (
    AICallRecord,
    CostEstimate,
    ProviderCallError,
    TaskInput,
    TaskOutput,
    TaskResult,
    TaskSpec,
    UnsupportedTaskError,
    result_type,
    utc_now,
)
from revue_portee.ai.costs import PriceTable, call_cost, estimate, estimate_tokens
from revue_portee.ai.prompts import RenderedPrompt, load_template
from revue_portee.config.secrets import SecretName, get_secret
from revue_portee.i18n import gettext as _

__all__ = ["PROVIDER_NAME", "AnthropicProvider", "UnsupportedParameterError", "output_schema"]

PROVIDER_NAME = "anthropic"
_SUPPORTED_PARAMS = frozenset({"max_tokens", "effort", "fallbacks", "thinking"})
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
# JSON Schema keywords that structured outputs do not accept; Pydantic still checks them.
_UNSUPPORTED_KEYWORDS = frozenset(
    {
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
        "pattern",
        "default",
    }
)


class UnsupportedParameterError(ValueError):
    def __init__(self, names: Sequence[str]) -> None:
        super().__init__(
            _("Unsupported parameter(s) for the Anthropic provider: {names}.").format(
                names=", ".join(sorted(names))
            )
        )


class _Message(Protocol):
    """The parts of an SDK message that are used (``Message`` or ``BetaMessage``)."""

    id: str
    model: str
    stop_reason: str | None
    content: Sequence[Any]
    usage: Any

    def to_dict(self) -> dict[str, Any]: ...


# Keywords whose value maps names (fields, definitions) to schemas: those names are
# kept as they are, whatever they are called.
_NAMED_SCHEMAS = frozenset({"properties", "$defs", "definitions"})


def _clean(node: JsonValue) -> JsonValue:
    if isinstance(node, list):
        return [_clean(child) for child in node]
    if not isinstance(node, dict):
        return node
    cleaned: dict[str, JsonValue] = {}
    for key, value in node.items():
        if key in _NAMED_SCHEMAS and isinstance(value, dict):
            cleaned[key] = {name: _clean(schema) for name, schema in value.items()}
        elif key not in _UNSUPPORTED_KEYWORDS:
            cleaned[key] = _clean(value)
    if cleaned.get("type") == "object":
        cleaned["additionalProperties"] = False
    return cleaned


def output_schema(model: type[BaseModel]) -> dict[str, JsonValue]:
    """JSON schema of ``model`` in the subset accepted by structured outputs."""
    schema = _clean(cast(JsonValue, model.model_json_schema()))
    assert isinstance(schema, dict)  # noqa: S101 - a model schema is always an object
    return schema


def _default_client(api_key: SecretStr) -> Any:  # noqa: ANN401 - the SDK client
    return anthropic.Anthropic(api_key=api_key.get_secret_value(), max_retries=2)


def _default_api_key() -> SecretStr:
    return get_secret(SecretName.ANTHROPIC_API_KEY)


class AnthropicProvider:
    """Runs tasks with one Claude model, one call per input."""

    def __init__(
        self,
        *,
        model: str,
        params: Mapping[str, JsonValue],
        prices: PriceTable,
        expected_output_tokens: int,
        clock: Callable[[], datetime] = utc_now,
        api_key: Callable[[], SecretStr] = _default_api_key,
        client_factory: Callable[[SecretStr], Any] = _default_client,
    ) -> None:
        unknown = set(params) - _SUPPORTED_PARAMS
        if unknown:
            raise UnsupportedParameterError(sorted(unknown))
        self._model = model
        self._params = dict(params)
        self._prices = prices
        self._expected_output_tokens = expected_output_tokens
        self._clock = clock
        self._api_key = api_key
        self._client_factory = client_factory
        self._client: Any = None

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def supports(self, task: TaskSpec[Any, Any]) -> bool:
        try:
            return load_template(task.prompt.template_id).version == task.prompt.version
        except FileNotFoundError:
            return False

    def _check(self, task: TaskSpec[Any, Any]) -> None:
        if not self.supports(task):
            raise UnsupportedTaskError(self.name, task.name)

    def _render(self, task: TaskSpec[Any, Any], item: TaskInput) -> RenderedPrompt:
        return load_template(task.prompt.template_id).render(item)

    def estimate_cost[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> CostEstimate:
        self._check(task)
        schema = str(output_schema(task.output_model))
        prompts = [self._render(task, item) for item in inputs]
        system_tokens = sum(estimate_tokens(prompt.system) for prompt in prompts)
        other_tokens = sum(estimate_tokens(prompt.user + schema) for prompt in prompts)
        return estimate(
            self._prices,
            self.name,
            self._model,
            input_tokens=system_tokens + other_tokens,
            output_tokens=self._expected_output_tokens * len(inputs),
            cacheable_tokens=system_tokens,
        )

    def request_params(self) -> dict[str, JsonValue]:
        """Request parameters as sent (and recorded), without the messages."""
        request: dict[str, JsonValue] = {"max_tokens": self._params.get("max_tokens", 16000)}
        if "effort" in self._params:
            request["output_config"] = {"effort": self._params["effort"]}
        if "thinking" in self._params:
            request["thinking"] = self._params["thinking"]
        if "fallbacks" in self._params:
            request["fallbacks"] = self._params["fallbacks"]
            request["betas"] = [_FALLBACK_BETA]
        return request

    def _request(self, task: TaskSpec[Any, Any], prompt: RenderedPrompt) -> dict[str, Any]:
        request: dict[str, Any] = self.request_params()
        output_config = dict(request.get("output_config") or {})
        output_config["format"] = {
            "type": "json_schema",
            "schema": output_schema(task.output_model),
        }
        request["output_config"] = output_config
        request["model"] = self._model
        # The instructions are a stable prefix: cached across inputs (ENF-COU-04).
        request["system"] = [
            {"type": "text", "text": prompt.system, "cache_control": {"type": "ephemeral"}}
        ]
        request["messages"] = [{"role": "user", "content": prompt.user}]
        return request

    def _send(self, request: dict[str, Any]) -> _Message:
        if self._client is None:
            self._client = self._client_factory(self._api_key())
        if "betas" in request:
            return cast(_Message, self._client.beta.messages.create(**request))
        return cast(_Message, self._client.messages.create(**request))

    def run[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> Iterator[TaskResult[OutputT]]:
        self._check(task)
        return self._results(task, inputs)

    def _results[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> Iterator[TaskResult[OutputT]]:
        for item in inputs:
            yield self._run_one(task, item)

    def _record(
        self,
        prompt: RenderedPrompt,
        task: TaskSpec[Any, Any],
        *,
        started: datetime,
        latency_ms: int,
        message: _Message | None = None,
        error_code: str | None = None,
        request_id: str | None = None,
    ) -> AICallRecord:
        """Call record. Without a message (the API answered with an error, or not at all),
        no model was returned: ``model_returned`` stays empty and the cost is zero."""
        usage = None if message is None else message.usage
        tokens = {
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "cache_read_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            "cache_write_tokens": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        }
        returned = None if message is None else message.model
        cost = Decimal(0)
        if message is not None:
            cost = call_cost(
                self._prices,
                self.name,
                _priced_model(self._prices, message.model, self._model),
                **tokens,
            )
            request_id = getattr(message, "_request_id", None) or message.id
        return AICallRecord(
            provider=self.name,
            model_requested=self._model,
            model_returned=returned,
            provider_request_id=request_id,
            prompt_template_id=task.prompt.template_id,
            prompt_template_version=task.prompt.version,
            prompt_sha256=prompt.sha256,
            params=self.request_params(),
            input_tokens=tokens["input_tokens"],
            output_tokens=tokens["output_tokens"],
            cache_read_tokens=tokens["cache_read_tokens"],
            cache_write_tokens=tokens["cache_write_tokens"],
            cost_estimate=cost,
            currency=self._prices.currency,
            latency_ms=latency_ms,
            status="ok" if error_code is None else "error",
            error_code=error_code,
            created_at=started,
        )

    def _run_one[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], item: InputT
    ) -> TaskResult[OutputT]:
        prompt = self._render(task, item)
        request = self._request(task, prompt)
        started = self._clock()
        start = time.perf_counter()
        try:
            message = self._send(request)
        except anthropic.APIError as error:
            latency = int((time.perf_counter() - start) * 1000)
            call = self._record(
                prompt,
                task,
                started=started,
                latency_ms=latency,
                error_code=type(error).__name__,
                request_id=getattr(error, "request_id", None),
            )
            raise ProviderCallError(
                _api_error_message(error), item_id=item.item_id, call=call
            ) from error
        latency = int((time.perf_counter() - start) * 1000)
        raw = cast(JsonValue, message.to_dict())
        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        failure: str | None = None
        output: OutputT | None = None
        if message.stop_reason in {"refusal", "max_tokens"}:
            failure = str(message.stop_reason)
        else:
            try:
                output = task.output_model.model_validate_json(text)
            except ValidationError:
                failure = "invalid_output"
        call = self._record(
            prompt, task, started=started, latency_ms=latency, message=message, error_code=failure
        )
        if output is None:
            raise ProviderCallError(
                _failure_message(failure or "invalid_output"),
                item_id=item.item_id,
                call=call,
                raw_response=raw,
            )
        return result_type(task.output_model)(
            item_id=item.item_id, output=output, call=call, raw_response=raw
        )


def _priced_model(prices: PriceTable, returned: str, requested: str) -> str:
    """Price the model that answered when it is known (e.g. after a fallback)."""
    known = prices.providers.get(PROVIDER_NAME, {})
    return returned if returned in known else requested


def _failure_message(code: str) -> str:
    messages = {
        "refusal": _("The model declined to answer this request."),
        "max_tokens": _("The answer of the model was cut off (maximum number of tokens)."),
        "invalid_output": _("The answer of the model does not match the expected format."),
    }
    return messages[code]


def _api_error_message(error: anthropic.APIError) -> str:
    if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return _(
            "The Anthropic API refused the key: check REVUE_PORTEE_ANTHROPIC_KEY "
            "(or ANTHROPIC_API_KEY)."
        )
    if isinstance(error, anthropic.APIConnectionError):
        return _(
            "The Anthropic API cannot be reached: check the network connection "
            "(the domain api.anthropic.com must be allowed)."
        )
    if isinstance(error, anthropic.RateLimitError):
        return _("The Anthropic API limits the number of requests: try again later.")
    return _("The call to the Anthropic API failed ({error}).").format(error=type(error).__name__)
