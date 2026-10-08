"""Every version of a prompt template has its entry in the development journal
(docs/08-journal-des-gabarits.md, RAISE 2 §1): changing a template without saying how
it was developed and tested fails the suite."""

from importlib.resources import files
from pathlib import Path

import yaml

JOURNAL = Path(__file__).parents[2] / "docs" / "08-journal-des-gabarits.md"


def template_versions() -> list[tuple[str, str]]:
    prompts = files("revue_portee.ai.prompts")
    found = []
    for folder in prompts.iterdir():
        meta = folder / "meta.yaml"
        if meta.is_file():
            data = yaml.safe_load(meta.read_text(encoding="utf-8"))
            found.append((str(data["id"]), str(data["version"])))
    return sorted(found)


def test_every_template_version_has_a_journal_entry() -> None:
    headings = {
        line.removeprefix("### ").strip()
        for line in JOURNAL.read_text(encoding="utf-8").splitlines()
        if line.startswith("### ")
    }
    versions = template_versions()
    assert len(versions) >= 4  # screen_reference, suggest_pcc, qualify…, suggest_terms
    missing = [f"{template} v{version}" for template, version in versions]
    missing = [entry for entry in missing if entry not in headings]
    assert missing == [], f"add these entries to {JOURNAL.name}: {missing}"
