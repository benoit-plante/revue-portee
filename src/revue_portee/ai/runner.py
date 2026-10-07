"""Provider-agnostic task execution used by application services."""

from collections.abc import Sequence

from revue_portee.ai.base import (
    ModelProvider,
    TaskInput,
    TaskOutput,
    TaskResult,
    TaskSpec,
    UnsupportedTaskError,
)

__all__ = ["run_task"]


def run_task[InputT: TaskInput, OutputT: TaskOutput](
    provider: ModelProvider, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
) -> list[TaskResult[OutputT]]:
    """Run ``task`` on every input and check that each input got exactly one result."""
    if not provider.supports(task):
        raise UnsupportedTaskError(provider.name, task.name)
    results = list(provider.run(task, inputs))
    expected = [item.item_id for item in inputs]
    received = [result.item_id for result in results]
    if sorted(received) != sorted(expected):
        raise RuntimeError(
            f"Le fournisseur « {provider.name} » a renvoyé {len(results)} résultat(s) "
            f"pour {len(inputs)} entrée(s) de la tâche « {task.name} »."
        )
    for result in results:
        if not isinstance(result.output, task.output_model):
            raise TypeError(f"Sortie invalide pour la tâche « {task.name} ».")
    return results
