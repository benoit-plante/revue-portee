import shutil
import subprocess
from pathlib import Path

import pytest

from revue_portee import __version__
from revue_portee.version import commit_of, tool_version

GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(GIT is None, reason="git is not installed")


def git(cwd: Path, *args: str) -> str:
    assert GIT is not None
    return subprocess.run(  # noqa: S603 - fixed git arguments in a temporary repository
        [GIT, *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def init_repo(root: Path) -> str:
    git(root, "init", "-q")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q",
        "--allow-empty", "-m", "init")  # fmt: skip
    return git(root, "rev-parse", "--short=12", "HEAD")


def test_commit_of_a_revue_portee_checkout(tmp_path: Path) -> None:
    package = tmp_path / "src" / "revue_portee"
    package.mkdir(parents=True)
    expected = init_repo(tmp_path)
    assert commit_of(package) == expected


def test_installed_copy_inside_another_repository_reports_no_commit(tmp_path: Path) -> None:
    # A wheel installed in the .venv of a research project that is itself a git repo.
    package = tmp_path / ".venv" / "lib" / "site-packages" / "revue_portee"
    package.mkdir(parents=True)
    init_repo(tmp_path)
    assert commit_of(package) is None


def test_outside_any_repository(tmp_path: Path) -> None:
    assert commit_of(tmp_path) is None


def test_tool_version_format() -> None:
    assert tool_version().startswith(f"{__version__} (")
