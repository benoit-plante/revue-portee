"""Current time, always timezone-aware UTC (ENF-TRA-01: dates in UTC, ISO 8601)."""

from datetime import UTC, datetime

__all__ = ["utc_now"]


def utc_now() -> datetime:
    return datetime.now(UTC)
