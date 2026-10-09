"""Norms and settings stored as dated YAML files (docs/03-architecture.md §1, principle 4):
reporting checklists, OSF form, flow diagram template, model prices, default AI
configuration."""

from functools import cache
from importlib.resources import files
from typing import Any

import yaml

from revue_portee.ai.costs import PriceTable
from revue_portee.ai.settings import AISettings
from revue_portee.domain.grid import GridTemplate
from revue_portee.domain.protocol import Checklist, OsfForm
from revue_portee.reporting.flow import FlowTemplate
from revue_portee.reporting.methods import ToolValidation

__all__ = [
    "default_ai_settings",
    "flow_template",
    "grid_template",
    "load_yaml",
    "osf_form",
    "peters_checklist",
    "price_table",
    "tool_validation",
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


@cache
def tool_validation() -> ToolValidation:
    return ToolValidation.model_validate(load_yaml("reporting/tool_validation.yaml"))


@cache
def grid_template() -> GridTemplate:
    """Starting extraction grid (JBI, Pollock et al., 2023)."""
    return GridTemplate.model_validate(load_yaml("extraction/jbi_pollock_2023.yaml"))
