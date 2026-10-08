"""Norms and settings stored as dated YAML files (docs/03-architecture.md §1, principle 4):
reporting checklists, OSF form, flow diagram template, model prices, default AI
configuration."""

from functools import cache
from importlib.resources import files
from typing import Any

import yaml

from revue_portee.ai.costs import PriceTable
from revue_portee.ai.settings import AISettings
from revue_portee.domain.protocol import Checklist, OsfForm
from revue_portee.reporting.flow import FlowTemplate

__all__ = [
    "default_ai_settings",
    "flow_template",
    "load_yaml",
    "osf_form",
    "peters_checklist",
    "price_table",
]


def load_yaml(name: str) -> Any:  # noqa: ANN401 - YAML documents are untyped until validated
    """Parse ``resources/<name>`` (a path relative to this package)."""
    resource = files("revue_portee.resources").joinpath(*name.split("/"))
    return yaml.safe_load(resource.read_text(encoding="utf-8"))


@cache
def price_table() -> PriceTable:
    return PriceTable.model_validate(load_yaml("model_prices.yaml"))


@cache
def default_ai_settings() -> AISettings:
    data = load_yaml("ai_defaults.yaml")
    return AISettings.model_validate({"supervision": data["supervision"], "tasks": data["tasks"]})


@cache
def peters_checklist() -> Checklist:
    return Checklist.model_validate(load_yaml("protocol/peters_2022.yaml"))


@cache
def osf_form() -> OsfForm:
    return OsfForm.model_validate(load_yaml("protocol/osf_gsrr.yaml"))


@cache
def flow_template() -> FlowTemplate:
    return FlowTemplate.model_validate(load_yaml("reporting/prisma_2020_flow.yaml"))
