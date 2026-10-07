"""Real calls to Claude, with the default project configuration (tranche 1.2).

Run only on explicit request: ``uv run pytest -m integration tests/integration/test_claude.py``.
They cost a few cents and need REVUE_PORTEE_ANTHROPIC_KEY (or ANTHROPIC_API_KEY) and
network access to api.anthropic.com.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from revue_portee.clock import utc_now
from revue_portee.domain.changes import ChangeType
from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.framing import Framing
from revue_portee.protocol import criteria, framing, qualification, suggestions
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import read_raw_response
from revue_portee.storage.repositories import ai as ai_repo
from support import TOOL_VERSION, new_project

pytestmark = pytest.mark.integration


@pytest.fixture
def folder(tmp_path: Path) -> Iterator[ProjectFolder]:
    project = new_project(tmp_path, utc_now)
    yield project
    project.close()


def check_calls(folder: ProjectFolder, task: str, count: int) -> None:
    with folder.engine.connect() as connection:
        calls = ai_repo.list_calls(connection, task=task)
    assert len(calls) == count
    for call in calls:
        record = call.record
        assert record.status == "ok"
        assert record.model_returned  # exact identifier returned by the API
        assert record.provider_request_id
        assert record.input_tokens > 0
        assert record.output_tokens > 0
        assert record.cost_estimate > 0
        assert record.response_path is not None
        raw = read_raw_response(folder.path, record.response_path)
        assert isinstance(raw, dict)
        assert raw["model"] == record.model_returned


def test_suggest_pcc_with_claude(folder: ProjectFolder) -> None:
    framing.save_framing(
        folder,
        Framing(
            question="Quelles interventions de soutien à la parentalité visent la santé "
            "mentale des enfants ?",
            population="Parents d'enfants de 0 à 12 ans",
        ),
        now=utc_now,
        tool_version=TOOL_VERSION,
    )
    preview = suggestions.preview_suggestions(folder)
    assert preview.estimate.amount > 0
    received = suggestions.request_suggestions(folder, now=utc_now, tool_version=TOOL_VERSION)
    assert received
    assert all(s.text for s in received)
    check_calls(folder, "suggest_pcc", 1)


def test_qualify_criterion_change_with_claude(folder: ProjectFolder) -> None:
    criteria.add_criterion(
        folder,
        pcc_element=PccElement.POPULATION,
        kind=CriterionKind.INCLUSION,
        text="Parents d'enfants de 0 à 12 ans",
        now=utc_now,
        tool_version=TOOL_VERSION,
    )
    criteria.activate_draft(folder, rationale="", now=utc_now, tool_version=TOOL_VERSION)
    criteria.update_criterion(
        folder,
        "P1",
        kind=CriterionKind.INCLUSION,
        text="Parents ou tuteurs d'enfants et d'adolescents de 0 à 17 ans",
        now=utc_now,
        tool_version=TOOL_VERSION,
    )
    (proposal,) = qualification.request_proposals(folder, now=utc_now, tool_version=TOOL_VERSION)
    # A wider age range and more caregivers: a careful reviewer calls it a broadening.
    assert proposal.change_type is ChangeType.BROADENING
    assert proposal.rationale
    check_calls(folder, "qualify_criterion_change", 1)
