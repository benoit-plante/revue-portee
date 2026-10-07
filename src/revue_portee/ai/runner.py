"""Provider-agnostic task execution used by application services."""

from collections import Counter
from collections.abc import Sequence

from revue_portee.ai.base import (
    ModelProvider,
    TaskInput,
    TaskOutput,
    TaskResult,
    TaskSpec,
    UnsupportedTaskError,
)
from revue_portee.i18n import gettext as _

__all__ = ["run_task"]


def run_task[InputT: TaskInput, OutputT: TaskOutput](
    provider: ModelProvider, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
) -> list[TaskResult[OutputT]]:
    """Run ``task`` on every input and check that each input got exactly one result."""
    if not provider.supports(task):
        raise UnsupportedTaskError(provider.name, task.name)
    results = list(provider.run(task, inputs))
    mismatch = _describe_mismatch(
        [item.item_id for item in inputs], [result.item_id for result in results]
    )
    if mismatch:
        raise RuntimeError(
            _(
                "The provider “{provider}” returned inconsistent results "
                "for the task “{task}”: {mismatch}."
            ).format(provider=provider.name, task=task.name, mismatch=mismatch)
        )
    for result in results:
        if not isinstance(result.output, task.output_model):
            raise TypeError(_("Invalid output for the task “{task}”.").format(task=task.name))
    return results


def _describe_mismatch(expected: Sequence[str], received: Sequence[str]) -> str:
    """Description of the item ids that are missing, unexpected or repeated."""
    expected_counts, received_counts = Counter(expected), Counter(received)
    missing = sorted((expected_counts - received_counts).keys())
    unexpected = sorted(set(received_counts) - set(expected_counts))
    repeated = sorted(
        item_id
        for item_id, count in received_counts.items()
        if item_id in expected_counts and count > expected_counts[item_id]
    )
    parts = [
        f"{label} {', '.join(ids)}"
        for label, ids in (
            (_("missing:"), missing),
            (_("unexpected:"), unexpected),
            (_("repeated:"), repeated),
        )
        if ids
    ]
    return "; ".join(parts)
