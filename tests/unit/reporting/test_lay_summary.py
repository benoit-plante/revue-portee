"""Plain-language summaries (EF-CON-01): versions, readability against the target of the
level, and the document, counted by hand."""

from datetime import UTC, datetime, timedelta

from revue_portee.domain.lay_summary import (
    TARGET_INDEX,
    LayLevel,
    LaySummary,
    SummaryStatus,
    current_summaries,
    meets_target,
    revised_summaries,
)
from revue_portee.domain.project import ReviewerKind
from revue_portee.domain.readability import readability
from revue_portee.reporting.document import render_markdown
from revue_portee.reporting.lay_summary import build_lay_summary

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def _summary(
    level: LayLevel, status: SummaryStatus, minutes: int, text: str = "Le chat dort. Il fait beau."
) -> LaySummary:
    return LaySummary(
        id=f"S{minutes}", level=level, language="fr", title="Ce que dit la recherche",
        text=text, status=status, reviewer_id="R",
        reviewer_kind=ReviewerKind.AI if status is SummaryStatus.PROPOSED else ReviewerKind.HUMAN,
        created_at=NOW + timedelta(minutes=minutes),
    )  # fmt: skip


def test_versions_and_targets() -> None:
    ai = _summary(LayLevel.GENERAL, SummaryStatus.PROPOSED, 1)
    own = _summary(LayLevel.GENERAL, SummaryStatus.REVISED, 2)
    later_ai = _summary(LayLevel.GENERAL, SummaryStatus.PROPOSED, 3)
    pro = _summary(LayLevel.PROFESSIONAL, SummaryStatus.REVISED, 4)
    found = [later_ai, ai, own, pro]
    assert current_summaries(found) == {LayLevel.GENERAL: later_ai, LayLevel.PROFESSIONAL: pro}
    assert revised_summaries(found) == {LayLevel.GENERAL: own, LayLevel.PROFESSIONAL: pro}
    assert [TARGET_INDEX[level] for level in LayLevel] == [60.0, 50.0, 30.0]
    # 42.2 (counted by hand in test_readability): under 50, over 30
    hard = readability("Les études incluses décrivent l'observance du traitement.", "fr")
    assert not meets_target(LayLevel.INFORMED, hard)
    assert meets_target(LayLevel.PROFESSIONAL, hard)
    assert not meets_target(LayLevel.GENERAL, None)
    two = _summary(LayLevel.GENERAL, SummaryStatus.REVISED, 5, "Un.\n\n\n  Deux.  \n\n")
    assert two.paragraphs == ("Un.", "Deux.")


def test_document_with_its_readability() -> None:
    own = _summary(LayLevel.GENERAL, SummaryStatus.REVISED, 2)
    text = render_markdown(
        build_lay_summary(
            own, level=LayLevel.GENERAL, review_title="Démo", language="fr", outdated=True,
            tool_version="0.1", generated_at=NOW,
        )
    )  # fmt: skip
    assert text.startswith("# Ce que dit la recherche")
    assert "revue de portée « Démo », pour le grand public." in text
    assert "À revoir : la synthèse narrative a été révisée depuis" in text
    assert "Le chat dort. Il fait beau." in text
    # 6 words, 2 sentences, 6 syllables: 130.4 (very easy), target 60 reached
    assert (
        "Indice de lisibilité (Kandel-Moles) : 130,4 (très facile) ; cible pour le "
        "grand public : 60 ou plus (cible atteinte). Calculé sur 6 mots, 2 phrases et "
        "6 syllabes."
    ) in text
    hard = _summary(
        LayLevel.INFORMED, SummaryStatus.REVISED, 3,
        "Les études incluses décrivent l'observance du traitement.",
    )  # fmt: skip
    english = render_markdown(
        build_lay_summary(hard, level=LayLevel.INFORMED, review_title="Demo", language="en",
                          outdated=False, tool_version="0.1", generated_at=NOW)
    )  # fmt: skip
    assert "target for informed readers: 50 or more (target not reached)" in english
    assert "To be reviewed" not in english


def test_level_without_revision() -> None:
    text = render_markdown(
        build_lay_summary(None, level=LayLevel.PROFESSIONAL, review_title="Démo", language="fr",
                          outdated=False, tool_version="0.1", generated_at=NOW)
    )  # fmt: skip
    assert text.startswith("# Démo : synthèse vulgarisée")
    assert "À rédiger : aucune synthèse révisée pour ce niveau." in text
    assert "Lisibilité" not in text
