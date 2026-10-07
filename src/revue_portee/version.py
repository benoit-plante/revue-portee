"""Tool version recorded in the journal and with each decision (ENF-REP-05)."""

import subprocess
from functools import cache
from pathlib import Path

from revue_portee import __version__

__all__ = ["tool_version"]


@cache
def _commit() -> str | None:
    """Short commit hash of the source tree, when running from a git checkout."""
    source = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],  # noqa: S607 - git from PATH
            cwd=source,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def tool_version() -> str:
    """``"<version> (<commit>)"``, or ``"<version> (commit inconnu)"`` outside git."""
    commit = _commit()
    return f"{__version__} ({commit})" if commit else f"{__version__} (commit inconnu)"
