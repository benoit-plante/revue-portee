"""Shared data of the screening tests: ten references, three criteria, and a
deterministic AI reviewer."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from revue_portee.ai.base import TaskInput
from revue_portee.ai.tasks.screening import ScreenReferenceInput

Clock = Callable[[], datetime]
TITLES = [
    "Housing insecurity among older adults in rural Quebec",
    "Home relocation of older adults and loneliness",
    "Logement et santé mentale des aînés à Montréal",
    "A protocol for a trial of housing support for older adults",
    "Childhood obesity and school meals",
    "Older adults and home adaptations: a qualitative study",
    "Software engineering practices in startups",
    "Housing first for homeless youth",
    "Caregivers of older adults living at home",
    "Air pollution and asthma in children",
]


def ris(titles: list[str]) -> bytes:
    records = []
    for i, title in enumerate(titles, start=1):
        abstract = "" if i == 2 else f"This study examines {title.lower()}."
        if i == 3:
            abstract = "Cette étude porte sur le logement et la santé des aînés dans la ville."
        records.append(
            f"TY  - JOUR\nTI  - {title}\nAU  - Author{i}, A.\nPY  - 2020\n"
            f"JO  - Journal {i}\nAB  - {abstract}\nER  - \n"
        )
    return "\n".join(records).encode("utf-8")


def answer(item: TaskInput) -> dict[str, Any]:
    """A deterministic reviewer: older adults and housing are looked for in the title."""
    assert isinstance(item, ScreenReferenceInput)
    title = item.reference.title.lower()
    older = "older" in title or "aînés" in title
    housing = "housing" in title or "logement" in title or "home" in title
    protocol = "protocol" in title
    # without an abstract, nothing tells the population: cannot tell
    status_p = ("met" if older else "not_met") if item.reference.abstract else "cannot_tell"
    status_c = "met" if housing else "not_met"
    keep = status_p == "met" and housing and not protocol
    unknown = status_p == "cannot_tell"
    return {
        "assessments": [
            {"code": "P1", "status": status_p, "evidence_quote": "older adults" if older else ""},
            {"code": "C1", "status": status_c, "evidence_quote": ""},
            {"code": "X1", "status": "met" if protocol else "not_met", "evidence_quote": ""},
        ],
        "decision": "include" if keep else ("uncertain" if unknown else "exclude"),
        "inclusion_probability": 0.9 if keep else (0.03 if not unknown else 0.04),
        "rationale": "P1 et C1 évalués.",
        "decisive_criteria": ["P1", "C1"],
    }
