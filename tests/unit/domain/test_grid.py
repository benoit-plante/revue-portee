"""Versioned extraction grid (EF-EXT-01, EF-EXT-02): typed fields, versions, diff."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from revue_portee.domain.criteria import (
    EmptyCriteriaError,
    ImmutableVersionError,
    MissingRationaleError,
    VersionStatus,
)
from revue_portee.domain.grid import (
    FieldType,
    GridField,
    activate,
    diff_versions,
    field_sort_key,
    first_draft,
    new_draft_from,
    next_field_code,
    supersede,
    with_fields,
)
from revue_portee.resources import grid_template

T0 = datetime(2026, 10, 9, tzinfo=UTC)
COUNTRY = GridField(code="D1", label="Pays", type=FieldType.TEXT)
DESIGN = GridField(
    code="D2", label="Devis", type=FieldType.SINGLE_CHOICE, choices=("Qualitatif", "Quantitatif")
)


def test_field_types_and_choices() -> None:
    assert DESIGN.choices == ("Qualitatif", "Quantitatif")
    with pytest.raises(ValidationError, match="at least two choices"):
        GridField(code="D3", label="Devis", type=FieldType.MULTIPLE_CHOICE, choices=("A",))
    with pytest.raises(ValidationError, match="distinct"):
        GridField(code="D3", label="Devis", type=FieldType.HIERARCHICAL, choices=("A", "A"))
    with pytest.raises(ValidationError, match="only choice fields"):
        GridField(code="D3", label="Âge", type=FieldType.NUMBER, choices=("A", "B"))
    with pytest.raises(ValidationError):
        GridField(code="X1", label="Code", type=FieldType.TEXT)


def test_codes_are_never_reused() -> None:
    assert next_field_code([]) == "D1"
    assert next_field_code(["D1", "D3", "nope"]) == "D4"  # D2 discarded, never given again
    assert sorted(["D10", "D2", "D1"], key=field_sort_key) == ["D1", "D2", "D10"]
    assert field_sort_key("other") > field_sort_key("D99")


def test_versions_and_diff() -> None:
    draft = with_fields(first_draft(version_id="V1", author_id="R", now=T0), [DESIGN, COUNTRY])
    with pytest.raises(EmptyCriteriaError):
        activate(first_draft(version_id="V0", author_id="R", now=T0), rationale="", now=T0)
    v1 = activate(draft, rationale="", now=T0)
    assert v1.status is VersionStatus.ACTIVE
    assert [f.code for f in v1.sorted_fields()] == ["D1", "D2"]
    assert v1.field("D9") is None
    with pytest.raises(ImmutableVersionError):
        with_fields(v1, [COUNTRY])
    with pytest.raises(ImmutableVersionError):
        activate(v1, rationale="", now=T0)
    with pytest.raises(ValueError, match="active or superseded"):
        new_draft_from(draft, version_id="V2", author_id="R", now=T0)
    v2 = new_draft_from(v1, version_id="V2", author_id="R", now=T0)
    sample = GridField(code="D3", label="Échantillon", type=FieldType.NUMBER)
    changed = DESIGN.model_copy(update={"choices": ("Qualitatif", "Quantitatif", "Mixte")})
    v2 = with_fields(v2, [changed, sample])
    with pytest.raises(MissingRationaleError):
        activate(v2, rationale=" ", now=T0)
    v2 = activate(v2, rationale="Méthodes mixtes ajoutées.", now=T0)
    delta = diff_versions(v1, v2)
    assert [f.code for f in delta.added] == ["D3"]
    assert [f.code for f in delta.removed] == ["D1"]
    assert [(m.code, m.changed) for m in delta.modified] == [("D2", ("choices",))]
    assert not delta.is_empty
    assert diff_versions(v1, v1).unchanged == ("D1", "D2")
    assert diff_versions(v1, v1).is_empty
    assert supersede(v1).status is VersionStatus.SUPERSEDED
    with pytest.raises(ValueError, match="only the active"):
        supersede(v2.model_copy(update={"status": VersionStatus.SUPERSEDED}))
    with pytest.raises(ValidationError, match="unique"):
        with_fields(first_draft(version_id="V9", author_id="R", now=T0), [COUNTRY, COUNTRY])


def test_starting_grid() -> None:
    template = grid_template()
    french = template.fields_in("fr")
    assert len(french) == 11
    assert french[0][:2] == ("Pays", FieldType.TEXT)
    assert french[2][3][0] == "Étude empirique quantitative"
    assert template.fields_in("es")[0][0] == "Country"  # English when the language is missing
    assert "Pollock" in template.source
