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


ENV_ACCESSORS = {"environ", "environb", "getenv", "getenvb"}


def environment_accesses(source: str) -> list[int]:
    """Line numbers where ``source`` reads the environment through the ``os`` module.

    Catches ``os.environ``, ``os.getenv``, aliases (``import os as o; o.environ``) and
    direct imports (``from os import environ``), not only the literal text.
    """
    tree = ast.parse(source)
    os_aliases = {"os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            os_aliases.update(
                alias.asname or alias.name for alias in node.names if alias.name == "os"
            )
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            if any(alias.name in ENV_ACCESSORS | {"*"} for alias in node.names):
                lines.append(node.lineno)
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in ENV_ACCESSORS
            and isinstance(node.value, ast.Name)
            and node.value.id in os_aliases
        ):
            lines.append(node.lineno)
    return lines


def test_environment_access_detection() -> None:
    assert environment_accesses("import os\nos.environ['X']\n") == [2]
    assert environment_accesses("import os as o\no.getenv('X')\n") == [2]
    assert environment_accesses("from os import environ\n") == [1]
    assert environment_accesses("from os import *\n") == [1]
    assert environment_accesses("import os\nos.path.join('a')\n") == []


def test_only_secrets_module_reads_environment() -> None:
    allowed = {PACKAGE_DIR / "config" / "secrets.py"}
    for path in PACKAGE_DIR.rglob("*.py"):
        if path not in allowed:
            lines = environment_accesses(path.read_text(encoding="utf-8"))
            assert not lines, f"{path.name} reads the environment (lines {lines})"


def test_only_the_anthropic_provider_imports_the_sdk() -> None:
    allowed = {PACKAGE_DIR / "ai" / "providers" / "anthropic.py"}
    for path in PACKAGE_DIR.rglob("*.py"):
        if path not in allowed:
            assert "anthropic" not in imported_roots(path), path.name


def test_services_do_not_name_providers() -> None:
    """Use cases only know ModelProvider and TaskSpec (CLAUDE.md, principle 4)."""
    for path in (PACKAGE_DIR / "protocol").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "AnthropicProvider" not in source, path.name
        assert "providers.anthropic" not in source, path.name
