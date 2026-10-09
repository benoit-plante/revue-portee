"""The narrative synthesis as a document (EF-SYN-04): revised sentences only, each
followed by the studies it rests on; a field without revision says so."""

from datetime import UTC, datetime

from revue_portee.domain.grid import FieldType, GridField
from revue_portee.domain.narrative import DraftStatus, NarrativeDraft, NarrativeSentence
from revue_portee.domain.project import ReviewerKind
from revue_portee.reporting.document import render_markdown
from revue_portee.reporting.narrative import NarrativeSection, build_narrative, cited

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
DESIGN = GridField(code="D1", label="Devis", type=FieldType.TEXT)
SETTING = GridField(code="D2", label="Milieu", type=FieldType.TEXT)
REFERENCES = [
    ("A", "Tremblay 2019", "Tremblay, A. Housing. J Aging. 2019"),
    ("B", "Roy et al. 2020", "Roy, B; Côté, C. Loneliness. 2020"),
    ("C", "Gagnon 2021", "Gagnon, D. Not cited. 2021"),
]


def _draft(*sentences: NarrativeSentence) -> NarrativeDraft:
    return NarrativeDraft(
        id="N1", field_code="D1", grid_version_id="G", language="fr", sentences=sentences,
        status=DraftStatus.REVISED, reviewer_id="R", reviewer_kind=ReviewerKind.HUMAN,
        created_at=NOW,
    )  # fmt: skip


def test_revised_sentences_with_their_studies() -> None:
    draft = _draft(
        NarrativeSentence(text="Deux études sont qualitatives.", study_ids=("A", "B")),
        NarrativeSentence(text="Une étude porte sur le logement", study_ids=("A",)),
    )
    sections = [
        NarrativeSection(field=DESIGN, revised=draft, outdated=True),
        NarrativeSection(field=SETTING, revised=None),
    ]
    text = render_markdown(
        build_narrative(
            sections,
            REFERENCES,
            project_title="Démo",
            language="fr",
            tool_version="0.1",
            generated_at=NOW,
        )
    )
    assert "# Démo : synthèse narrative (ébauche)" in text
    assert (
        "Deux études sont qualitatives (Roy et al. 2020 ; Tremblay 2019). "
        "Une étude porte sur le logement (Tremblay 2019)."
    ) in text
    assert "À revoir : des valeurs ou le champ ont changé depuis cette révision." in text
    assert "À rédiger : aucune synthèse révisée pour ce champ." in text
    # only the studies cited are listed, in alphabetical order
    assert "- Roy et al. 2020. Roy, B; Côté, C. Loneliness. 2020\n- Tremblay 2019." in text
    assert "Gagnon" not in text


def test_in_english_and_without_citation() -> None:
    assert cited(["A", "Z"], {"A": "Roy 2020"}, "en") == "(Roy 2020; Z)"
    text = render_markdown(
        build_narrative(
            [NarrativeSection(field=DESIGN, revised=None)],
            REFERENCES,
            project_title="Demo",
            language="en",
            tool_version="0.1",
            generated_at=NOW,
        )
    )
    assert "To be written: no revised synthesis of this field." in text
    assert "Studies cited" not in text
