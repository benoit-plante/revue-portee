"""Versions of the extraction grid reported as deviations from the protocol (EF-VER-07):
from version 2 on, activated after the registration."""

from datetime import UTC, date, datetime, timedelta

from revue_portee.domain.criteria import VersionStatus
from revue_portee.domain.grid import FieldType, GridField, GridVersion
from revue_portee.domain.protocol import ProtocolRegistration
from revue_portee.protocol.document import _grid_deviations

T0 = datetime(2026, 10, 9, tzinfo=UTC)
A = GridField(code="D1", label="Pays", type=FieldType.TEXT)
B = GridField(code="D2", label="Taille", type=FieldType.NUMBER)


def _version(number: int, fields: tuple[GridField, ...], day: int) -> GridVersion:
    return GridVersion(
        id=f"V{number}", number=number, parent_id=None if number == 1 else f"V{number - 1}",
        status=VersionStatus.ACTIVE, created_at=T0, activated_at=T0 + timedelta(days=day),
        author_id="R", rationale=f"r{number}", fields=fields,
    )  # fmt: skip


def test_versions_after_the_registration() -> None:
    versions = [
        _version(1, (A,), 0),
        _version(2, (A, B), 1),  # before the registration: in the protocol
        _version(3, (B.model_copy(update={"definition": "n"}),), 5),
    ]
    registration = ProtocolRegistration(
        id="r", doi="10.17605/OSF.IO/ABCDE", registered_on=date(2026, 10, 12),
        criteria_version_id=None, created_at=T0 + timedelta(days=3), reviewer_id="R",
    )  # fmt: skip
    assert _grid_deviations(versions, None) == ()
    (found,) = _grid_deviations(versions, registration)
    assert (found.number, found.rationale) == (3, "r3")
    assert (found.added, found.modified, found.removed) == ((), ("D2",), ("D1",))
