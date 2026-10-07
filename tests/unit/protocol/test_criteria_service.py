from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from revue_portee.domain.criteria import (
    CriterionKind,
    ImmutableVersionError,
    MissingRationaleError,
    PccElement,
    VersionStatus,
)
from revue_portee.domain.framing import Framing
from revue_portee.domain.journal import EntryType
from revue_portee.protocol import criteria, framing, notes
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import criteria as repo
from support import TOOL_VERSION, make_clock, new_project

Clock = Callable[[], datetime]

POP, CON, CTX, OTH = (
    PccElement.POPULATION,
    PccElement.CONCEPT,
    PccElement.CONTEXT,
    PccElement.OTHER,
)
INC, EXC = CriterionKind.INCLUSION, CriterionKind.EXCLUSION

SIX = [
    (POP, INC, "Parents ou tuteurs d'enfants de 0 à 12 ans"),
    (POP, EXC, "Enfants avec un diagnostic de trouble du spectre de l'autisme"),
    (CON, INC, "Intervention de soutien à la parentalité"),
    (CON, INC, "Résultat mesuré sur la santé mentale de l'enfant"),
    (CTX, INC, "Services communautaires ou de première ligne"),
    (OTH, EXC, "Langue autre que le français ou l'anglais"),
]


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProjectFolder, Clock]]:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    yield folder, clock
    folder.close()


def add_six(folder: ProjectFolder, clock: Clock) -> None:
    for element, kind, text_ in SIX:
        criteria.add_criterion(
            folder, pcc_element=element, kind=kind, text=text_, now=clock, tool_version=TOOL_VERSION
        )


def test_six_criteria_with_stable_codes(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    framing.save_framing(
        folder,
        Framing(
            question="Quelles interventions de soutien à la parentalité ont été étudiées ?",
            population="Parents d'enfants de 0 à 12 ans",
            concept="Soutien à la parentalité; santé mentale de l'enfant",
            context="Services communautaires",
        ),
        now=clock,
        tool_version=TOOL_VERSION,
    )
    add_six(folder, clock)
    v1 = criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    assert [c.code for c in v1.sorted_criteria()] == ["P1", "P2", "C1", "C2", "CTX1", "X1"]
    assert v1.number == 1
    assert v1.status is VersionStatus.ACTIVE


def test_modifying_a_criterion_creates_version_2(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    add_six(folder, clock)
    v1 = criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)

    criteria.update_criterion(
        folder,
        "P1",
        kind=INC,
        text="Parents ou tuteurs d'enfants de 0 à 17 ans",
        examples=["Familles recomposées"],
        now=clock,
        tool_version=TOOL_VERSION,
    )
    state = criteria.criteria_state(folder)
    assert state.active == v1  # still in force, unchanged
    assert state.draft is not None
    assert state.draft.number == 2

    with pytest.raises(MissingRationaleError):
        criteria.activate_draft(folder, rationale=" ", now=clock, tool_version=TOOL_VERSION)
    v2 = criteria.activate_draft(
        folder, rationale="Élargir à l'adolescence", now=clock, tool_version=TOOL_VERSION
    )
    assert (v2.number, v2.parent_id, v2.status) == (2, v1.id, VersionStatus.ACTIVE)

    old = criteria.version(folder, 1)
    assert old.status is VersionStatus.SUPERSEDED
    assert old.criterion("P1").text == "Parents ou tuteurs d'enfants de 0 à 12 ans"  # type: ignore[union-attr]
    delta = criteria.diff(folder, 1, 2)
    assert [(m.code, m.changed_fields) for m in delta.modified] == [("P1", ("text", "examples"))]
    assert delta.added == delta.removed == ()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE criterion SET text = 'x' WHERE code = 'P1'",
        "DELETE FROM criterion WHERE code = 'P1'",
        "INSERT INTO criterion (version_id, code, pcc_element, kind, text) "
        "VALUES (:version_id, 'P9', 'population', 'inclusion', 'x')",
        "UPDATE criteria_version SET rationale = 'réécrit'",
        "UPDATE criteria_version SET status = 'draft'",
        "DELETE FROM criteria_version",
    ],
)
def test_database_refuses_changes_to_the_active_version(
    setup: tuple[ProjectFolder, Clock], statement: str
) -> None:
    folder, clock = setup
    add_six(folder, clock)
    v1 = criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    query = text(statement)
    if ":version_id" in statement:
        query = query.bindparams(version_id=v1.id)
    with pytest.raises(IntegrityError, match="immutable"), folder.engine.begin() as connection:
        connection.execute(query)
    assert criteria.version(folder, 1) == v1


def test_repository_reports_immutable_version(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    add_six(folder, clock)
    v1 = criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    with pytest.raises(ImmutableVersionError), folder.engine.begin() as connection:
        repo.replace_draft_criteria(connection, v1)


def test_codes_are_never_reused(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    add_six(folder, clock)
    criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    criteria.remove_criterion(folder, "X1", now=clock, tool_version=TOOL_VERSION)
    added = criteria.add_criterion(
        folder, pcc_element=OTH, kind=INC, text="Études publiées depuis 2000",
        now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    assert added.code == "X2"
    v2 = criteria.activate_draft(
        folder, rationale="Remplacer X1", now=clock, tool_version=TOOL_VERSION
    )
    delta = criteria.diff(folder, 1, 2)
    assert [c.code for c in delta.removed] == ["X1"]
    assert [c.code for c in delta.added] == ["X2"]
    assert v2.criterion("X1") is None


def test_discard_draft_keeps_active_version(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    add_six(folder, clock)
    v1 = criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    criteria.remove_criterion(folder, "P2", now=clock, tool_version=TOOL_VERSION)
    criteria.discard_draft(folder, now=clock, tool_version=TOOL_VERSION)
    state = criteria.criteria_state(folder)
    assert (state.active, state.draft) == (v1, None)
    with pytest.raises(criteria.NoDraftError):
        criteria.discard_draft(folder, now=clock, tool_version=TOOL_VERSION)
    with pytest.raises(criteria.NoDraftError):
        criteria.activate_draft(folder, rationale="x", now=clock, tool_version=TOOL_VERSION)


def test_unknown_criterion_and_version(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    with pytest.raises(criteria.UnknownCriterionError, match="Critère inconnu"):
        criteria.update_criterion(
            folder, "P7", kind=INC, text="x", now=clock, tool_version=TOOL_VERSION
        )
    with pytest.raises(criteria.UnknownCriterionError):
        criteria.remove_criterion(folder, "P7", now=clock, tool_version=TOOL_VERSION)
    with pytest.raises(criteria.UnknownVersionError, match="Version des critères inconnue"):
        criteria.version(folder, 3)


def test_unchanged_update_and_framing_are_not_journaled(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    criteria.add_criterion(
        folder, pcc_element=POP, kind=INC, text="A", now=clock, tool_version=TOOL_VERSION
    )
    question = Framing(question="Q ?")
    framing.save_framing(folder, question, now=clock, tool_version=TOOL_VERSION)
    count = len(notes.journal_entries(folder))
    criteria.update_criterion(
        folder, "P1", kind=INC, text="A", now=clock, tool_version=TOOL_VERSION
    )
    same = framing.save_framing(folder, question, now=clock, tool_version=TOOL_VERSION)
    assert same.number == 1
    assert len(notes.journal_entries(folder)) == count


def test_every_action_is_journaled_and_chain_verifies(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    framing.save_framing(folder, Framing(question="Q1 ?"), now=clock, tool_version=TOOL_VERSION)
    framing.save_framing(folder, Framing(question="Q2 ?"), now=clock, tool_version=TOOL_VERSION)
    add_six(folder, clock)
    criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    criteria.update_criterion(
        folder, "C2", kind=EXC, text="Autre", now=clock, tool_version=TOOL_VERSION
    )
    criteria.activate_draft(folder, rationale="Clarifier C2", now=clock, tool_version=TOOL_VERSION)
    notes.add_note(folder, "Réunion d'équipe : C2 reformulé", now=clock, tool_version=TOOL_VERSION)

    types = [e.entry_type for e in notes.journal_entries(folder)]
    assert types == [
        EntryType.PROJECT_CREATED,
        EntryType.FRAMING_UPDATED,
        EntryType.FRAMING_UPDATED,
        EntryType.CRITERIA_DRAFT_STARTED,
        *[EntryType.CRITERIA_DRAFT_EDITED] * 6,
        EntryType.CRITERIA_VERSION_CREATED,
        EntryType.CRITERIA_DRAFT_STARTED,
        EntryType.CRITERIA_DRAFT_EDITED,
        EntryType.CRITERIA_VERSION_CREATED,
        EntryType.NOTE_ADDED,
    ]
    entries = notes.journal_entries(folder)
    version_2 = entries[-2]
    assert version_2.payload["changes"] == {"added": [], "removed": [], "modified": ["C2"]}
    assert version_2.payload["rationale"] == "Clarifier C2"
    assert version_2.summary_fr == "Version 2 des critères en vigueur"
    assert all(e.actor_reviewer_id == folder.reviewer_id for e in entries)
    assert notes.verify_journal(folder).valid
    with folder.engine.connect() as connection:
        stored = connection.execute(
            text("SELECT journal_entry_id FROM criteria_version WHERE number = 2")
        ).scalar_one()
    assert stored == version_2.id


def test_empty_note_is_refused(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    with pytest.raises(notes.EmptyNoteError, match="vide"):
        notes.add_note(folder, "   ", now=clock, tool_version=TOOL_VERSION)


def test_codes_of_discarded_or_removed_draft_criteria_are_never_reused(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    criteria.add_criterion(
        folder, pcc_element=POP, kind=INC, text="A", now=clock, tool_version=TOOL_VERSION
    )
    criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    # P2 only ever exists in a draft that is discarded.
    added = criteria.add_criterion(
        folder, pcc_element=POP, kind=INC, text="Adultes", now=clock, tool_version=TOOL_VERSION
    )
    assert added.code == "P2"
    criteria.discard_draft(folder, now=clock, tool_version=TOOL_VERSION)
    # P3 is added then removed within the same draft.
    p3 = criteria.add_criterion(
        folder, pcc_element=POP, kind=INC, text="Aînés", now=clock, tool_version=TOOL_VERSION
    )
    criteria.remove_criterion(folder, p3.code, now=clock, tool_version=TOOL_VERSION)
    later = criteria.add_criterion(
        folder,
        pcc_element=POP,
        kind=INC,
        text="Familles d'accueil",
        now=clock,
        tool_version=TOOL_VERSION,
    )
    assert (p3.code, later.code) == ("P3", "P4")


def test_code_registry_is_append_only(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    criteria.add_criterion(
        folder, pcc_element=POP, kind=INC, text="A", now=clock, tool_version=TOOL_VERSION
    )
    for statement in ("DELETE FROM criterion_code", "UPDATE criterion_code SET code = 'P9'"):
        with (
            pytest.raises(IntegrityError, match="append-only"),
            folder.engine.begin() as connection,
        ):
            connection.execute(text(statement))


def test_unchanged_edit_of_the_active_version_starts_no_draft(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    criteria.add_criterion(
        folder,
        pcc_element=POP,
        kind=INC,
        text="A",
        examples=["e"],
        now=clock,
        tool_version=TOOL_VERSION,
    )
    criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    count = len(notes.journal_entries(folder))
    criteria.update_criterion(
        folder,
        "P1",
        kind=INC,
        text=" A ",
        examples=["e", " "],
        now=clock,
        tool_version=TOOL_VERSION,
    )
    assert criteria.criteria_state(folder).draft is None
    assert len(notes.journal_entries(folder)) == count
