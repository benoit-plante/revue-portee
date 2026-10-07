from datetime import UTC, datetime, timedelta

import pytest

from revue_portee.domain.criteria import PccElement
from revue_portee.domain.ids import is_ulid, new_ulid, next_criterion_code, ulid_timestamp_ms

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def test_ulid_shape_and_timestamp() -> None:
    value = new_ulid(NOW)
    assert len(value) == 26
    assert is_ulid(value)
    assert ulid_timestamp_ms(value) == int(NOW.timestamp() * 1000)


def test_ulid_hand_computed_vectors() -> None:
    # Crockford base 32, most significant digit first: 1 ms -> "...01", 32 ms -> "...10".
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    assert new_ulid(epoch + timedelta(milliseconds=1), bytes(10))[:10] == "0000000001"
    assert new_ulid(epoch + timedelta(milliseconds=32), bytes(10))[:10] == "0000000010"
    assert ulid_timestamp_ms("00000000Z9" + "0" * 16) == 31 * 32 + 9
    assert new_ulid(epoch, randomness=bytes(10)) == "0" * 26
    assert new_ulid(epoch, randomness=b"\xff" * 10) == "0" * 10 + "Z" * 16


def test_ulids_sort_by_creation_time() -> None:
    earlier = new_ulid(NOW, randomness=b"\xff" * 10)
    later = new_ulid(NOW + timedelta(milliseconds=1), randomness=bytes(10))
    assert earlier < later


@pytest.mark.parametrize("value", ["", "01ARZ3NDEKTSV4RRFFQ69G5FA", "8" + "0" * 25, "0" * 25 + "U"])
def test_invalid_ulids(value: str) -> None:
    assert not is_ulid(value)
    with pytest.raises(ValueError, match="not a ULID"):
        ulid_timestamp_ms(value)


def test_ulid_rejects_naive_or_bad_input() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        new_ulid(datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="10 bytes"):
        new_ulid(NOW, randomness=b"short")
    with pytest.raises(ValueError, match="range"):
        new_ulid(datetime(1969, 12, 31, tzinfo=UTC))


@pytest.mark.parametrize(
    ("element", "used", "expected"),
    [
        (PccElement.POPULATION, [], "P1"),
        (PccElement.POPULATION, ["P1", "P2", "C1"], "P3"),
        (PccElement.CONCEPT, ["P1", "C9", "C10"], "C11"),
        (PccElement.CONTEXT, ["C1", "X4"], "CTX1"),
        (PccElement.OTHER, ["X1", "X3"], "X4"),  # X2 removed earlier: never reused
        (PccElement.CONTEXT, ["CTX2", "not-a-code"], "CTX3"),
    ],
)
def test_next_criterion_code(element: PccElement, used: list[str], expected: str) -> None:
    assert next_criterion_code(element, used) == expected
