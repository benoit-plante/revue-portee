"""Reporting checklists of the review stored as data (EF-DEC-02, ENF-NOR-03): each item
names the project data that can fill it (« sources »). A new version of a checklist is
a new file: the code that fills the items does not change."""

import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["ReportingChecklist", "ReportingItem"]


class ReportingItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    section: str = Field(min_length=1)  # title, abstract, introduction, methods…
    en: str = Field(min_length=1)
    fr: str = Field(min_length=1)
    optional: bool = False
    sources: tuple[str, ...] = ()

    def label(self, language: str) -> str:
        return self.fr if language == "fr" else self.en


class ReportingChecklist(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    published: dt.date
    source: str
    verified: bool
    items: tuple[ReportingItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate item ids")
        return self
