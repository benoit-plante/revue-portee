"""Impact of a change of the extraction grid (EF-VER-06): sets of studies touched,
values to review and fields due to the AI, on cases built by hand."""

from datetime import UTC, datetime, timedelta

from pydantic import JsonValue

from revue_portee.domain.criteria import VersionStatus
from revue_portee.domain.extraction import (
    ChangeKind,
    ExtractionValue,
    ValueStatus,
    fields_due,
    grid_impact,
    holds_value,
    stale,
)
from revue_portee.domain.grid import FieldType, GridField, GridVersion, diff_versions
from revue_portee.domain.project import ReviewerKind

T0 = datetime(2026, 10, 9, tzinfo=UTC)
COUNTRY = GridField(code="D1", label="Pays", type=FieldType.TEXT)
SIZE = GridField(code="D2", label="Taille", type=FieldType.NUMBER)
SIZE_DEFINED = SIZE.model_copy(update={"definition": "Participants analysed"})
DESIGN = GridField(code="D3", label="Devis", type=FieldType.SINGLE_CHOICE, choices=("A", "B"))
SETTING = GridField(code="D4", label="Milieu", type=FieldType.TEXT)


def _version(vid: str, number: int, *fields: GridField) -> GridVersion:
    return GridVersion(
        id=vid, number=number, parent_id=None if number == 1 else "V1",
        status=VersionStatus.ACTIVE, fields=fields, created_at=T0, activated_at=T0,
        author_id="R",
    )  # fmt: skip


V1 = _version("V1", 1, COUNTRY, SIZE, DESIGN)
V2 = _version("V2", 2, COUNTRY, SIZE_DEFINED, SETTING)  # D2 defined, D3 removed, D4 added
V3 = _version("V3", 3, COUNTRY, SIZE, SETTING)  # D2 back to its first definition
VERSIONS = {v.id: v for v in (V1, V2, V3)}
_clock = iter(range(1000))


def _value(
    study: str,
    code: str,
    *,
    version: str = "V1",
    kind: ReviewerKind = ReviewerKind.AI,
    status: ValueStatus = ValueStatus.PROPOSED,
    value: JsonValue = "x",
) -> ExtractionValue:
    tick = next(_clock)
    return ExtractionValue(
        id=f"E{tick:04d}", reference_id=study, field_code=code, grid_version_id=version,
        reported=status is not ValueStatus.REJECTED, value=value, status=status,
        reviewer_id="R", reviewer_kind=kind, created_at=T0 + timedelta(seconds=tick),
    )  # fmt: skip


def _human(study: str, code: str, status: ValueStatus, **kwargs: object) -> ExtractionValue:
    return _value(study, code, kind=ReviewerKind.HUMAN, status=status, **kwargs)  # type: ignore[arg-type]


# S1: D1 proposed by the AI; D2 proposed then validated; D3 proposed then corrected.
# S2: D2 proposed then rejected (no value); D3 proposed. S3: nothing yet.
VALUES = [
    _value("S1", "D1"),
    _value("S1", "D2", value=24),
    _human("S1", "D2", ValueStatus.VALIDATED, value=24),
    _value("S1", "D3", value="A"),
    _human("S1", "D3", ValueStatus.CORRECTED, value="B"),
    _value("S2", "D2", value=10),
    _human("S2", "D2", ValueStatus.REJECTED, value=None),
    _value("S2", "D3", value="A"),
]


def test_studies_touched_by_each_change() -> None:
    impact = grid_impact(diff_versions(V1, V2), ["S1", "S2", "S3"], VALUES)
    assert [(c.kind, c.code, c.studies) for c in impact] == [
        (ChangeKind.ADDED, "D4", ("S1", "S2", "S3")),  # every study, to complete
        (ChangeKind.MODIFIED, "D2", ("S1",)),  # S2's value was rejected: none to review
        (ChangeKind.REMOVED, "D3", ("S1", "S2")),  # archived, the AI's included
    ]
    assert impact[1].changed == ("definition",)
    assert impact[1].label == "Taille"


def test_only_included_studies_are_touched() -> None:
    impact = grid_impact(diff_versions(V1, V2), ["S2"], VALUES)
    assert [c.studies for c in impact] == [("S2",), (), ("S2",)]
    assert grid_impact(diff_versions(V1, V1), ["S1"], VALUES) == ()


def test_values_to_review_follow_the_definition_in_force() -> None:
    given = _human("S1", "D2", ValueStatus.VALIDATED)
    assert stale(given, VERSIONS, SIZE_DEFINED)  # given before the definition
    assert not stale(given, VERSIONS, SIZE)  # the field went back to it (version 3)
    assert not stale(_value("S1", "D1"), VERSIONS, COUNTRY)
    assert stale(_value("S1", "D1", version="GONE"), VERSIONS, COUNTRY)
    assert stale(_value("S1", "D4"), VERSIONS, SETTING)  # no D4 in version 1
    assert not holds_value(None)
    assert not holds_value(_human("S2", "D2", ValueStatus.REJECTED))
    assert holds_value(_value("S2", "D2", value=None))  # « not reported » is a value


def test_fields_due_to_the_ai() -> None:
    s1 = [v for v in VALUES if v.reference_id == "S1"]
    # D1 answered under its definition; D2 to review; D4 new
    assert [f.code for f in fields_due(V2, VERSIONS, s1)] == ["D2", "D4"]
    confirmed = [*s1, _human("S1", "D2", ValueStatus.VALIDATED, version="V2")]
    assert [f.code for f in fields_due(V2, VERSIONS, confirmed)] == ["D4"]
    # in a pilot, the AI answers every field it has not answered under its definition
    assert [f.code for f in fields_due(V2, VERSIONS, confirmed, pilot=True)] == ["D2", "D4"]
    assert [f.code for f in fields_due(V2, VERSIONS, [])] == ["D1", "D2", "D4"]
    answered = [*confirmed, _value("S1", "D4", version="V2")]
    assert fields_due(V2, VERSIONS, answered) == ()
