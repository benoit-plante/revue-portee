"""ENF-SEC-04: no versioned (or about to be versioned) file under ``tests/`` holds a secret."""

import subprocess
from pathlib import Path

from revue_portee.config.secret_scan import scan_file
from revue_portee.config.secrets import SecretName, get_optional_secret

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests"


def candidate_files() -> list[Path]:
    """Tracked and untracked-but-not-ignored files under ``tests/``."""
    try:
        listing = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "tests"],  # noqa: S607
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        ).stdout.decode()
        files = [REPO_ROOT / name for name in listing.split("\0") if name]
    except (OSError, subprocess.CalledProcessError):
        files = [p for p in TESTS_DIR.rglob("*") if "__pycache__" not in p.parts]
    return sorted(p for p in files if p.is_file())


def configured_secret_values() -> list[str]:
    values = []
    for name in SecretName:
        secret = get_optional_secret(name)
        if secret is not None:
            values.append(secret.get_secret_value())
    return values


def test_scan_covers_test_files() -> None:
    files = candidate_files()
    assert Path(__file__).resolve() in files
    assert (TESTS_DIR / "conftest.py") in files


def test_no_secret_in_tests_directory() -> None:
    forbidden = configured_secret_values()
    findings = [
        finding
        for path in candidate_files()
        for finding in scan_file(
            path, forbidden=forbidden, display=str(path.relative_to(REPO_ROOT))
        )
    ]
    # Findings name the file, line and kind only: the values themselves are never shown.
    assert not findings, "Secrets suspects dans tests/ :\n" + "\n".join(map(str, findings))
