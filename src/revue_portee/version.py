"""Tool version recorded in the journal and with each decision (ENF-REP-05)."""

import subprocess
from functools import cache
from pathlib import Path

from revue_portee import __version__

__all__ = ["commit_of", "tool_version"]


@cache
def _commit() -> str | None:
    return commit_of(Path(__file__).resolve().parent)


def commit_of(package: Path) -> str | None:
    """Short commit hash of the revue-portee checkout that contains ``package``, if any.

    Only a git work tree whose ``src/revue_portee`` is this very package counts: an
    installed copy that merely sits inside some other repository (for example a
    research project's own ``.venv``) must not report that repository's commit.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel", "--short=12", "HEAD"],  # noqa: S607
            cwd=package,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = result.stdout.split()
    if len(lines) != 2:
        return None
    toplevel, commit = lines
    if (Path(toplevel) / "src" / "revue_portee").resolve() != package.resolve():
        return None
    return commit


def tool_version() -> str:
    """``"<version> (<commit>)"``, or ``"<version> (commit inconnu)"`` outside git."""
    commit = _commit()
    return f"{__version__} ({commit})" if commit else f"{__version__} (commit inconnu)"
