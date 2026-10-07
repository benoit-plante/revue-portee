from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from revue_portee.domain.criteria import (
    CriteriaVersion,
    Criterion,
    CriterionKind,
    EmptyCriteriaError,
    ImmutableVersionError,
    MissingRationaleError,
    PccElement,
    VersionStatus,
    activate,
    code_sort_key,
    diff_versions,
    first_draft,
    new_draft_from,
    supersede,
    with_criteria,
)

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
INC, EXC = CriterionKind.INCLUSION, CriterionKind.EXCLUSION
ELEMENT = {"P": PccElement.POPULATION, "C": PccElement.CONCEPT, "CTX": PccElement.CONTEXT}


def crit(code: str, text: str, kind: CriterionKind = INC, **extra: object) -> Criterion:
    prefix = code.rstrip("0123456789")
    element = ELEMENT.get(prefix, PccElement.OTHER)
    return Criterion.model_validate(
        {"code": code, "pcc_element": element, "kind": kind, "text": text} | extra
    )


def version(number: int, *criteria: Criterion) -> CriteriaVersion:
    return CriteriaVersion(
        id=f"V{number}",
        number=number,
        parent_id=None if number == 1 else f"V{number - 1}",
        status=VersionStatus.ACTIVE,
        created_at=NOW,
        activated_at=NOW,
        author_id="R1",
        rationale="" if number == 1 else "change",
        criteria=criteria,
    )


# Six criteria of the demonstration review (parenting support and child mental health).
P1 = crit("P1", "Parents ou tuteurs d'enfants de 0 à 12 ans")
P2 = crit("P2", "Enfants avec diagnostic de trouble du spectre de l'autisme", EXC)
C1 = crit("C1", "Intervention de soutien à la parentalité")
CTX1 = crit("CTX1", "Services communautaires ou de première ligne")
X1 = crit("X1", "Étude primaire publiée de 2000 à 2026")
X2 = crit("X2", "Langue de publication autre que le français ou l'anglais", EXC)
V1 = version(1, P1, P2, C1, CTX1, X1, X2)


# --- Diff: 5 cases computed by hand (docs/04-feuille-de-route.md, tranche 1.1) ---------


def test_diff_case_1_identical_versions() -> None:
    diff = diff_versions(V1, version(2, P1, P2, C1, CTX1, X1, X2))
    assert diff.is_empty
    assert diff.unchanged == ("P1", "P2", "C1", "CTX1", "X1", "X2")


def test_diff_case_2_one_criterion_added() -> None:
    x3 = crit("X3", "Littérature grise exclue", EXC)
    diff = diff_versions(V1, version(2, P1, P2, C1, CTX1, X1, X2, x3))
    assert diff.added == (x3,)
    assert diff.removed == ()
    assert diff.modified == ()


def test_diff_case_3_one_criterion_removed() -> None:
    diff = diff_versions(V1, version(2, P1, C1, CTX1, X1, X2))
    assert diff.removed == (P2,)
    assert diff.added == ()
    assert diff.modified == ()
    assert len(diff.unchanged) == 5


def test_diff_case_4_one_text_reworded() -> None:
    p1_new = crit("P1", "Parents ou tuteurs d'enfants de 0 à 17 ans")
    diff = diff_versions(V1, version(2, p1_new, P2, C1, CTX1, X1, X2))
    assert [(m.code, m.changed_fields) for m in diff.modified] == [("P1", ("text",))]
    assert diff.modified[0].before == P1
    assert diff.modified[0].after == p1_new


def test_diff_case_5_mixed_changes_in_code_order() -> None:
    p1_kind = crit("P1", P1.text, EXC)
    c1_examples = crit("C1", C1.text, examples=("Programme Triple P",))
    p3 = crit("P3", "Familles d'accueil")
    c2 = crit("C2", "Intervention en ligne")
    new = version(2, c2, CTX1, p3, X1, c1_examples, X2, p1_kind)  # input order is irrelevant
    diff = diff_versions(V1, new)
    assert [c.code for c in diff.added] == ["P3", "C2"]
    assert [c.code for c in diff.removed] == ["P2"]
    assert [(m.code, m.changed_fields) for m in diff.modified] == [
        ("P1", ("kind",)),
        ("C1", ("examples",)),
    ]
    assert diff.unchanged == ("CTX1", "X1", "X2")
    assert (diff.from_number, diff.to_number) == (1, 2)


# --- Versions --------------------------------------------------------------------------


def test_lifecycle_v1_then_v2() -> None:
    draft = with_criteria(first_draft(version_id="V1", author_id="R1", now=NOW), [P1, C1])
    v1 = activate(draft, rationale="", now=NOW)
    assert v1.status is VersionStatus.ACTIVE
    assert v1.activated_at == NOW

    draft2 = new_draft_from(v1, version_id="V2", author_id="R1", now=NOW)
    assert (draft2.number, draft2.parent_id, draft2.criteria) == (2, "V1", v1.criteria)
    draft2 = with_criteria(draft2, [P1, C1, X1])
    v2 = activate(draft2, rationale="  Ajout de la période  ", now=NOW)
    assert v2.rationale == "Ajout de la période"
    assert supersede(v1).status is VersionStatus.SUPERSEDED
    # v1 itself is unchanged: versions are values, never mutated.
    assert v1.status is VersionStatus.ACTIVE
    assert v1.criterion("X1") is None


def test_active_version_cannot_be_modified() -> None:
    with pytest.raises(ImmutableVersionError):
        with_criteria(V1, [P1])
    with pytest.raises(ImmutableVersionError):
        activate(V1, rationale="again", now=NOW)
    with pytest.raises(ValidationError):
        V1.number = 3  # type: ignore[misc]  # frozen model


def test_superseded_version_cannot_be_modified_or_superseded_again() -> None:
    old = supersede(V1)
    with pytest.raises(ImmutableVersionError):
        with_criteria(old, [P1])
    with pytest.raises(ValueError, match="active"):
        supersede(old)


def test_activation_rules() -> None:
    empty = first_draft(version_id="V1", author_id="R1", now=NOW)
    with pytest.raises(EmptyCriteriaError):
        activate(empty, rationale="", now=NOW)
    draft2 = new_draft_from(V1, version_id="V2", author_id="R1", now=NOW)
    with pytest.raises(MissingRationaleError):
        activate(draft2, rationale="   ", now=NOW)
    with pytest.raises(ValueError, match="active or superseded"):
        new_draft_from(empty, version_id="V3", author_id="R1", now=NOW)


def test_version_invariants() -> None:
    with pytest.raises(ValidationError, match="unique"):
        version(1, P1, P1)
    with pytest.raises(ValidationError, match="parent"):
        CriteriaVersion(
            id="V2", number=2, parent_id=None, status=VersionStatus.DRAFT,
            created_at=NOW, author_id="R1",
        )  # fmt: skip
    with pytest.raises(ValidationError, match="activated_at"):
        CriteriaVersion(
            id="V1", number=1, parent_id=None, status=VersionStatus.ACTIVE,
            created_at=NOW, author_id="R1",
        )  # fmt: skip


@pytest.mark.parametrize(
    ("code", "element"),
    [("P1", PccElement.CONCEPT), ("CTX1", PccElement.CONCEPT), ("X1", PccElement.POPULATION)],
)
def test_code_must_match_pcc_element(code: str, element: PccElement) -> None:
    with pytest.raises(ValidationError, match="does not match"):
        Criterion(code=code, pcc_element=element, kind=INC, text="x")


@pytest.mark.parametrize("code", ["p1", "P0", "Q1", "P01", "CTX"])
def test_invalid_codes(code: str) -> None:
    with pytest.raises(ValidationError):
        Criterion(code=code, pcc_element=PccElement.POPULATION, kind=INC, text="x")


def test_code_sort_key_is_natural() -> None:
    codes = ["X1", "P10", "C1", "P9", "CTX2", "P1", "CTX10", "zz"]
    assert sorted(codes, key=code_sort_key) == [
        "P1",
        "P9",
        "P10",
        "C1",
        "CTX2",
        "CTX10",
        "X1",
        "zz",
    ]
    assert [c.code for c in version(1, X1, C1, P2, P1).sorted_criteria()] == [
        "P1",
        "P2",
        "C1",
        "X1",
    ]
