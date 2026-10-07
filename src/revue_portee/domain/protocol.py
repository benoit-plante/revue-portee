"""Review protocol: sections, reporting checklists, registration (EF-CAD-06 to 08).

The protocol is generated from the project data (framing, criteria, AI configuration)
and from free-text sections written by the team. Free text is versioned like the rest
of the method: each change is a new immutable version.
"""

import re
from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "DOI_PATTERN",
    "FREE_TEXT_SECTIONS",
    "Checklist",
    "ChecklistItem",
    "OsfForm",
    "OsfItem",
    "ProtocolRegistration",
    "ProtocolSection",
    "ProtocolText",
    "ProtocolTextVersion",
    "normalize_doi",
]


class ProtocolSection(StrEnum):
    """Sections of the generated protocol, in document order."""

    TITLE = "title"
    TEAM = "team"
    ABSTRACT = "abstract"
    BACKGROUND = "background"
    EXISTING_REVIEWS = "existing_reviews"
    OBJECTIVES = "objectives"
    QUESTIONS = "questions"
    PARTICIPANTS = "participants"
    CONCEPT = "concept"
    CONTEXT = "context"
    SOURCES = "sources"
    METHODS_FRAMEWORK = "methods_framework"
    SEARCH = "search"
    INFORMATION_SOURCES = "information_sources"
    SELECTION = "selection"
    AI_USE = "ai_use"
    EXTRACTION = "extraction"
    ANALYSIS = "analysis"
    APPRAISAL = "appraisal"
    CONSULTATION = "consultation"
    DEVIATIONS = "deviations"
    ACKNOWLEDGEMENTS = "acknowledgements"
    FUNDING = "funding"
    CONFLICTS = "conflicts"
    REFERENCES = "references"
    APPENDICES = "appendices"


# Sections whose content is written by the team (the others are generated, possibly
# completed by free text: see reporting/protocol.py).
FREE_TEXT_SECTIONS: tuple[ProtocolSection, ...] = (
    ProtocolSection.ABSTRACT,
    ProtocolSection.BACKGROUND,
    ProtocolSection.EXISTING_REVIEWS,
    ProtocolSection.OBJECTIVES,
    ProtocolSection.SOURCES,
    ProtocolSection.SEARCH,
    ProtocolSection.INFORMATION_SOURCES,
    ProtocolSection.SELECTION,
    ProtocolSection.EXTRACTION,
    ProtocolSection.ANALYSIS,
    ProtocolSection.APPRAISAL,
    ProtocolSection.CONSULTATION,
    ProtocolSection.ACKNOWLEDGEMENTS,
    ProtocolSection.FUNDING,
    ProtocolSection.CONFLICTS,
    ProtocolSection.REFERENCES,
)


class ProtocolText(BaseModel):
    """Free text of the protocol, by section (blank sections are dropped)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sections: dict[ProtocolSection, str] = Field(default_factory=dict)

    @field_validator("sections")
    @classmethod
    def _only_free_text(cls, value: dict[ProtocolSection, str]) -> dict[ProtocolSection, str]:
        unknown = set(value) - set(FREE_TEXT_SECTIONS)
        if unknown:
            raise ValueError(f"not free-text sections: {sorted(unknown)}")
        return {
            section: value[section].strip()
            for section in FREE_TEXT_SECTIONS
            if value.get(section, "").strip()
        }

    def text(self, section: ProtocolSection) -> str:
        return self.sections.get(section, "")


class ProtocolTextVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    number: int = Field(ge=1)
    created_at: AwareDatetime
    author_id: str
    text: ProtocolText


# DOI syntax (Crossref recommendation): "10." + registrant code + "/" + suffix.
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")
# Resolver and label prefixes accepted in front of a DOI.
_DOI_PREFIX = re.compile(r"^(?:(?:https?://)?(?:dx\.|www\.)?doi\.org/|doi:\s*)", re.IGNORECASE)


def normalize_doi(value: str) -> str:
    """DOI without resolver prefix, upper-cased (DOIs are case-insensitive).

    Accepts ``10.…``, ``doi:10.…`` (with or without a space), ``doi.org/…`` and
    ``http(s)://(dx.|www.)doi.org/…``. Raises ValueError if the text is not a DOI.
    """
    doi = _DOI_PREFIX.sub("", value.strip(), count=1).strip()
    if not DOI_PATTERN.match(doi):
        raise ValueError("not a DOI")
    return doi.upper()


class ProtocolRegistration(BaseModel):
    """Registration of the protocol (EF-CAD-08): afterwards, any new criteria version
    is a deviation from the protocol to be reported."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    doi: str
    registered_on: date
    criteria_version_id: str | None
    created_at: AwareDatetime
    reviewer_id: str

    @field_validator("doi")
    @classmethod
    def _doi(cls, value: str) -> str:
        return normalize_doi(value)


class ChecklistItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    section: ProtocolSection
    en: str = Field(min_length=1)
    fr: str = Field(min_length=1)
    optional: bool = False

    def label(self, language: str) -> str:
        return self.fr if language == "fr" else self.en


class Checklist(BaseModel):
    """Reporting checklist stored as data (docs/03-architecture.md §1, principle 4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: str
    source: str
    verified: bool
    items: tuple[ChecklistItem, ...]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("checklist item ids must be unique")
        return self


class OsfItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^GSRRF-\d+$")
    en: str = Field(min_length=1)
    fr: str = Field(min_length=1)
    sections: tuple[ProtocolSection, ...] = ()

    def label(self, language: str) -> str:
        return self.fr if language == "fr" else self.en


class OsfForm(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: str
    source: str
    verified: bool
    items: tuple[OsfItem, ...]

    @model_validator(mode="after")
    def _numbered(self) -> Self:
        expected = [f"GSRRF-{n}" for n in range(1, len(self.items) + 1)]
        if [item.id for item in self.items] != expected:
            raise ValueError("OSF items must be numbered GSRRF-1, GSRRF-2, … in order")
        return self
