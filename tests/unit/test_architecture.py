"""Guards on the rules of docs/03-architecture.md and CLAUDE.md."""

import ast
import re
import sys
from pathlib import Path

import revue_portee

PACKAGE_DIR = Path(revue_portee.__file__).parent
ALLOWED_IN_DOMAIN = {"pydantic", "revue_portee"}
MODEL_NAME = re.compile(r"\b(?:claude|gpt|gemini|llama|mistral|o\d)-[\w.\-]+", re.IGNORECASE)


def imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_domain_imports_only_stdlib_and_pydantic() -> None:
    for path in (PACKAGE_DIR / "domain").rglob("*.py"):
        external = imported_roots(path) - ALLOWED_IN_DOMAIN - set(sys.stdlib_module_names)
        assert not external, f"{path.name} imports {sorted(external)}"


def test_domain_does_not_import_other_layers() -> None:
    for path in (PACKAGE_DIR / "domain").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"revue_portee\.(?!domain\b)", source), path.name


def test_no_hard_coded_model_name() -> None:
    for path in PACKAGE_DIR.rglob("*.py"):
        assert not MODEL_NAME.search(path.read_text(encoding="utf-8")), path.name


def test_only_secrets_module_reads_environment() -> None:
    allowed = {PACKAGE_DIR / "config" / "secrets.py"}
    for path in PACKAGE_DIR.rglob("*.py"):
        if path not in allowed:
            source = path.read_text(encoding="utf-8")
            assert "os.environ" not in source, path.name
            assert "getenv" not in source, path.name
