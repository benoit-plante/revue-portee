"""Fixture of the screening tests: a project with active criteria and ten references."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from revue_portee.collect import imports
from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.protocol import criteria
from revue_portee.storage.project_folder import ProjectFolder
from support import TOOL_VERSION, make_clock, new_project

from .common import TITLES, Clock, ris


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProjectFolder, Clock]]:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    for element, kind, text in (
        (PccElement.POPULATION, CriterionKind.INCLUSION, "Older adults (65 and over)."),
        (PccElement.CONCEPT, CriterionKind.INCLUSION, "Housing or living conditions."),
        (PccElement.OTHER, CriterionKind.EXCLUSION, "Study protocols without results."),
    ):
        criteria.add_criterion(
            folder, pcc_element=element, kind=kind, text=text, now=clock, tool_version=TOOL_VERSION
        )
    criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    imports.import_ris(
        folder, "demo.ris", ris(TITLES), database="APA PsycInfo", now=clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    yield folder, clock
    folder.close()
