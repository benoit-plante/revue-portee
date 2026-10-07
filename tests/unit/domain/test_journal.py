from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from pydantic import ValidationError

from revue_portee.domain.journal import (
    GENESIS_HASH,
    EntryType,
    JournalEntry,
    canonical_json,
    entry_digest,
    seal,
    verify_chain,
)

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def chain(length: int) -> list[JournalEntry]:
    entries: list[JournalEntry] = []
    prev = GENESIS_HASH
    for index in range(length):
        entry = seal(
            entry_id=f"E{index}",
            created_at=NOW + timedelta(seconds=index),
            actor_reviewer_id="R1",
            entry_type=EntryType.NOTE_ADDED,
            summary_fr=f"Note {index} : réunion d'équipe",
            tool_version="0.1.0 (test)",
            prev_hash=prev,
            payload={"text": f"note {index}", "n": index, "tags": ["a", "é"]},
        )
        entries.append(entry)
        prev = entry.hash
    return entries


def test_valid_chain() -> None:
    entries = chain(4)
    assert entries[0].prev_hash == GENESIS_HASH
    assert all(b.prev_hash == a.hash for a, b in pairwise(entries))
    assert verify_chain(entries).valid
    assert verify_chain(entries).checked == 4
    assert verify_chain([]).valid


def test_altered_entry_fails_verification() -> None:
    entries = chain(4)
    entries[2] = entries[2].model_copy(update={"summary_fr": "Note modifiée après coup"})
    check = verify_chain(entries)
    assert not check.valid
    assert (check.first_invalid_index, check.first_invalid_id) == (2, "E2")
    assert check.reason == "content_altered"


@pytest.mark.parametrize("field", ["payload", "created_at", "actor_reviewer_id", "entry_type"])
def test_every_field_is_covered_by_the_digest(field: str) -> None:
    entries = chain(2)
    altered = {
        "payload": {"text": "autre"},
        "created_at": NOW + timedelta(days=1),
        "actor_reviewer_id": "R2",
        "entry_type": EntryType.FRAMING_UPDATED,
    }[field]
    entries[0] = entries[0].model_copy(update={field: altered})
    assert verify_chain(entries).first_invalid_index == 0


def test_removed_or_reordered_entries_break_the_links() -> None:
    entries = chain(4)
    removed = verify_chain([entries[0], entries[2], entries[3]])
    assert (removed.valid, removed.first_invalid_index, removed.reason) == (False, 1, "broken_link")
    swapped = verify_chain([entries[1], entries[0]])
    assert (swapped.first_invalid_index, swapped.reason) == (0, "broken_link")


def test_rehashing_one_entry_is_not_enough_to_hide_a_change() -> None:
    entries = chain(3)
    fields = entries[1].model_dump() | {"summary_fr": "falsifié"}
    forged = entries[1].model_copy(
        update={"summary_fr": "falsifié", "hash": entry_digest(fields, entries[1].prev_hash)}
    )
    check = verify_chain([entries[0], forged, entries[2]])
    assert (check.first_invalid_index, check.reason) == (2, "broken_link")


def test_digest_is_stable_across_timezones() -> None:
    entry = chain(1)[0]
    shifted = entry.model_dump() | {"created_at": NOW.astimezone(UTC).astimezone()}
    assert entry_digest(shifted, entry.prev_hash) == entry.hash


def test_canonical_json() -> None:
    assert canonical_json({"b": 1, "a": "é"}) == '{"a":"é","b":1}'


def test_entry_validation() -> None:
    with pytest.raises(ValidationError):
        seal(
            entry_id="E", created_at=NOW, actor_reviewer_id=None, entry_type="Bad Type",
            summary_fr="x", tool_version="t", prev_hash=GENESIS_HASH,
        )  # fmt: skip
