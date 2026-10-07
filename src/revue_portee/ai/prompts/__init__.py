"""Versioned prompt templates (docs/03-architecture.md §6.4).

Each template is a folder ``<id>/`` with ``meta.yaml`` (id, version, task, changelog),
``system.md.j2`` (fixed instructions: the stable prefix that benefits from prompt
caching) and ``user.md.j2`` (the task input). Changing a template means incrementing
its version. The SHA-256 of the rendered prompt is recorded with every call
(ENF-TRA-01).
"""

import hashlib
from functools import cache
from importlib.resources import files
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, ConfigDict, Field

from revue_portee.ai.base import PromptRef, TaskInput
from revue_portee.domain.journal import canonical_json

__all__ = ["PromptTemplate", "RenderedPrompt", "load_template", "prompt_ref"]

_ENV = Environment(  # noqa: S701 - prompts are plain text sent to a model, never HTML
    undefined=StrictUndefined, keep_trailing_newline=False, trim_blocks=True, lstrip_blocks=True
)


class RenderedPrompt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    system: str
    user: str

    @property
    def sha256(self) -> str:
        """Digest of exactly what is sent to the model (system and user parts)."""
        content = canonical_json({"system": self.system, "user": self.user})
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class PromptTemplate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: str = Field(min_length=1)
    task: str
    changelog: tuple[dict[str, str], ...] = ()
    system_source: str
    user_source: str

    @property
    def ref(self) -> PromptRef:
        return PromptRef(template_id=self.id, version=self.version)

    def render(self, item: TaskInput) -> RenderedPrompt:
        values: dict[str, Any] = item.model_dump(mode="json")
        return RenderedPrompt(
            system=_ENV.from_string(self.system_source).render(values).strip(),
            user=_ENV.from_string(self.user_source).render(values).strip(),
        )


@cache
def load_template(template_id: str) -> PromptTemplate:
    folder = files("revue_portee.ai.prompts") / template_id
    meta = yaml.safe_load((folder / "meta.yaml").read_text(encoding="utf-8"))
    if meta.get("id") != template_id:
        raise ValueError(f"prompt template {template_id}: id mismatch in meta.yaml")
    return PromptTemplate(
        id=meta["id"],
        version=str(meta["version"]),
        task=meta["task"],
        changelog=tuple({k: str(v) for k, v in entry.items()} for entry in meta["changelog"]),
        system_source=(folder / "system.md.j2").read_text(encoding="utf-8"),
        user_source=(folder / "user.md.j2").read_text(encoding="utf-8"),
    )


def prompt_ref(template_id: str) -> PromptRef:
    return load_template(template_id).ref
