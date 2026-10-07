"""Identifiers: ULIDs and stable criterion codes (docs/03-architecture.md §5).

ULIDs are implemented here with the standard library only, because the domain must
not depend on anything external except Pydantic.
"""

import os
import re
from collections.abc import Iterable
from datetime import datetime

from revue_portee.domain.criteria import CODE_PREFIXES, CRITERION_CODE, PccElement

__all__ = [
    "ULID_PATTERN",
    "is_ulid",
    "new_ulid",
    "next_criterion_code",
    "ulid_timestamp_ms",
]

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {char: index for index, char in enumerate(_CROCKFORD)}
ULID_PATTERN = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_MAX_TIMESTAMP_MS = (1 << 48) - 1


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        value, remainder = divmod(value, 32)
        chars.append(_CROCKFORD[remainder])
    return "".join(reversed(chars))


def new_ulid(now: datetime, randomness: bytes | None = None) -> str:
    """Return a ULID for ``now`` (timezone-aware): 48-bit milliseconds + 80 random bits.

    ULIDs sort by creation time, which keeps identifiers independent of any database
    sequence (docs/03-architecture.md §12).
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    timestamp_ms = int(now.timestamp() * 1000)
    if not 0 <= timestamp_ms <= _MAX_TIMESTAMP_MS:
        raise ValueError("timestamp out of ULID range")
    random_bytes = os.urandom(10) if randomness is None else randomness
    if len(random_bytes) != 10:
        raise ValueError("ULID randomness must be 10 bytes")
    return _encode(timestamp_ms, 10) + _encode(int.from_bytes(random_bytes, "big"), 16)


def is_ulid(value: str) -> bool:
    """Whether ``value`` is a canonical (upper-case) ULID."""
    return bool(ULID_PATTERN.match(value))


def ulid_timestamp_ms(value: str) -> int:
    """Milliseconds since the Unix epoch encoded in a ULID."""
    if not is_ulid(value):
        raise ValueError("not a ULID")
    result = 0
    for char in value[:10]:
        result = result * 32 + _DECODE[char]
    return result


def next_criterion_code(element: PccElement, used_codes: Iterable[str]) -> str:
    """Next free code for ``element``.

    ``used_codes`` must contain every code ever used in the project (all versions),
    so that a removed criterion's code is never reused for a different criterion.
    """
    prefix = CODE_PREFIXES[element]
    highest = 0
    for code in used_codes:
        match = CRITERION_CODE.match(code)
        if match and match.group("prefix") == prefix:
            highest = max(highest, int(match.group("number")))
    return f"{prefix}{highest + 1}"
