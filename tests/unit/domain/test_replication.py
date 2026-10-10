"""Comparators of the replication benchmark, each on a case computed by hand
(tests/fixtures/replication/README.md for the values of the fictitious review)."""

import math

import pytest

from revue_portee.domain.metrics import cohen_kappa_nominal, gwet_ac1_nominal
from revue_portee.domain.replication import (
    NOT_REPORTED,
    LossStage,
    Proportion,
    PublishedDistribution,
    PublishedFlow,
    StudyPath,
    categorical_agreement,
    distribution_gap,
    end_to_end,
    flow_gaps,
    loss_cascade,
    lost_at,
    screening_loss_descriptors,
    year_descriptors,
)

# --- Agreement on categories ----------------------------------------------------------

# D1 of the stepwise replay: (published, tool) for S1, S2, S4, S5, S6.
D1 = [("ER", "ER"), ("QE", "QE"), ("Q", "Q"), ("QE", "ER"), ("Q", "Q")]
# D3: « not reported » is a category of its own.
D3 = [("oui", "oui"), ("oui", "non"), (NOT_REPORTED, NOT_REPORTED), ("oui", "oui"),
      ("non", "non")]  # fmt: skip


def test_nominal_kappa_by_hand() -> None:
    # Expected agreement 0.2 x 0.4 + 0.4 x 0.2 + 0.4 x 0.4 = 0.32; (0.8 - 0.32) / 0.68.
    assert cohen_kappa_nominal(D1) == pytest.approx(0.48 / 0.68)
    # 0.6 x 0.4 + 0.2 x 0.4 + 0.2 x 0.2 = 0.36; (0.8 - 0.36) / 0.64.
    assert cohen_kappa_nominal(D3) == pytest.approx(0.6875)


def test_nominal_ac1_by_hand() -> None:
    # pi = 0.3, 0.3, 0.4: sum of pi(1 - pi) = 0.66, / (3 - 1) = 0.33; 0.47 / 0.67.
    assert gwet_ac1_nominal(D1) == pytest.approx(0.47 / 0.67)
    # pi = 0.5, 0.3, 0.2: 0.62 / 2 = 0.31; 0.49 / 0.69.
    assert gwet_ac1_nominal(D3) == pytest.approx(0.49 / 0.69)


def test_nominal_statistics_match_the_binary_ones() -> None:
    from revue_portee.domain.metrics import Confusion, cohen_kappa, gwet_ac1

    pairs = [("k", "k")] * 6 + [("k", "x")] * 2 + [("x", "k")] + [("x", "x")] * 3
    binary = Confusion(tp=6, fn=2, fp=1, tn=3)
    assert cohen_kappa_nominal(pairs) == pytest.approx(cohen_kappa(binary))
    assert gwet_ac1_nominal(pairs) == pytest.approx(gwet_ac1(binary))


def test_nominal_statistics_undefined() -> None:
    assert cohen_kappa_nominal([]) is None
    assert gwet_ac1_nominal([]) is None
    one_category = [("a", "a"), ("a", "a")]
    assert cohen_kappa_nominal(one_category) is None
    assert gwet_ac1_nominal(one_category) is None


def test_categorical_agreement() -> None:
    found = categorical_agreement("D3", D3)
    assert (found.compared, found.agreed) == (5, 4)
    assert found.agreement.value == pytest.approx(0.8)
    assert (found.not_reported_published, found.not_reported_tool) == (1, 1)
    assert found.kappa == pytest.approx(0.6875)
    assert found.ac1 == pytest.approx(0.49 / 0.69)


# --- Cascade --------------------------------------------------------------------------


def test_lost_at_each_step() -> None:
    assert lost_at(StudyPath(False, False, False, False, False)) is LossStage.OUT_OF_SEARCH
    assert lost_at(StudyPath(True, False, False, False, False)) is LossStage.SEARCH
    assert lost_at(StudyPath(True, True, False, False, False)) is LossStage.TITLE_ABSTRACT
    assert lost_at(StudyPath(True, True, True, False, False)) is LossStage.RETRIEVAL
    assert lost_at(StudyPath(True, True, True, True, False)) is LossStage.FULL_TEXT
    assert lost_at(StudyPath(True, True, True, True, True)) is None
    # Out of every database searched, but collected all the same: lost later, if at all.
    assert lost_at(StudyPath(False, True, True, True, True)) is None


def test_cascade_lists_every_step() -> None:
    paths = [
        StudyPath(True, True, True, True, True),  # S1
        StudyPath(True, True, True, True, False),  # S2
        StudyPath(True, True, True, True, False),
        StudyPath(False, False, False, False, False),  # S6
    ]
    assert loss_cascade(paths) == {
        LossStage.OUT_OF_SEARCH: 1,
        LossStage.SEARCH: 0,
        LossStage.TITLE_ABSTRACT: 0,
        LossStage.RETRIEVAL: 0,
        LossStage.FULL_TEXT: 2,
    }


# --- End to end -----------------------------------------------------------------------


def test_end_to_end_of_the_fictitious_review() -> None:
    published = ["S1", "S2", "S3", "S4", "S5", "S6"]
    retrievable = ["S1", "S2", "S3", "S4", "S5"]
    tool = [frozenset({"S1"}), frozenset(), frozenset()]  # S1 (+ S1b), R10, R11
    e = end_to_end(published, retrievable, tool)
    assert (e.published, e.retrievable, e.tool, e.matched, e.tool_matched) == (6, 5, 3, 1, 1)
    assert e.recall.value == pytest.approx(1 / 6)
    assert e.recall_retrievable.value == pytest.approx(1 / 5)
    assert e.precision.value == pytest.approx(1 / 3)
    assert e.f1 == pytest.approx(2 / 9)
    assert e.f1_retrievable == pytest.approx(0.25)
    assert e.jaccard == pytest.approx(1 / 8)
    assert e.jaccard_retrievable == pytest.approx(1 / 7)


def test_end_to_end_with_two_tool_studies_for_one_published_study() -> None:
    # The tool did not group two reports of A: both match A, B is missed, C is extra.
    e = end_to_end(["A", "B"], ["A", "B"], [frozenset({"A"}), frozenset({"A"}), frozenset()])
    assert (e.matched, e.tool_matched) == (1, 2)
    assert e.recall.value == pytest.approx(0.5)
    assert e.precision.value == pytest.approx(2 / 3)
    # Published 2, plus the one study of the tool that matches none.
    assert e.jaccard == pytest.approx(1 / 3)


def test_end_to_end_without_anything() -> None:
    e = end_to_end(["A"], [], [])
    assert e.precision.value is None
    assert e.f1 is None
    assert e.recall_retrievable.value is None
    assert e.jaccard == 0
    assert end_to_end([], [], []).jaccard is None


def test_proportion_interval() -> None:
    p = Proportion(4, 5)
    assert p.value == pytest.approx(0.8)
    assert p.interval == pytest.approx((0.3755, 0.9638), abs=1e-4)
    assert Proportion(0, 0).value is None
    assert Proportion(0, 0).interval is None


# --- Distributions --------------------------------------------------------------------


def test_distribution_gap_of_d1_chained() -> None:
    published = PublishedDistribution(
        field="D1", categories={"Essai randomisé": 1, "Quasi expérimental": 3, "Qualitatif": 2},
        n=6,
    )  # fmt: skip
    gap = distribution_gap(published, {"Essai randomisé": 2, "Quasi expérimental": 1}, 3)
    assert [c.category for c in gap.categories] == [
        "Essai randomisé", "Quasi expérimental", "Qualitatif"
    ]  # fmt: skip
    assert [c.gap for c in gap.categories] == pytest.approx([50.0, 50 / 3, 100 / 3])
    assert gap.within.count == 0
    assert gap.same_mode is False
    # Ranks (1, 3, 2) and (3, 2, 1): covariance -1, variances 2 and 2.
    assert gap.rank_correlation == pytest.approx(-0.5)


def test_distribution_gap_with_ties_and_extra_categories() -> None:
    published = PublishedDistribution(field="D1", categories={"ER": 1, "QE": 3, "Q": 2})
    assert published.total == 6
    gap = distribution_gap(published, {"ER": 2, "QE": 1, "Q": 2}, 5)
    # Ranks (1, 3, 2) and (2.5, 1, 2.5): covariance -1.5, variances 2 and 1.5.
    assert gap.rank_correlation == pytest.approx(-1.5 / math.sqrt(3))
    extra = distribution_gap(published, {"Autre": 1}, 1)
    assert extra.categories[-1].category == "Autre"
    assert extra.categories[-1].tool == pytest.approx(100.0)


def test_distribution_gap_same_mode_and_undefined_correlation() -> None:
    published = PublishedDistribution(field="D2", categories={"C": 2, "R": 2, "H": 2})
    gap = distribution_gap(published, {"C": 1, "R": 1, "H": 1}, 3)
    assert gap.within.count == 3
    assert gap.same_mode is True
    assert gap.rank_correlation is None
    single = PublishedDistribution(field="D2", categories={"C": 2})
    assert distribution_gap(single, {}, 0).rank_correlation is None
    assert distribution_gap(single, {}, 0).categories[0].tool == 0.0


# --- Flow diagram and descriptors -------------------------------------------------------


def test_flow_gaps_box_by_box() -> None:
    published = PublishedFlow(identified=30, after_duplicates=27, included_studies=6)
    gaps = flow_gaps(published, {"identified": 29, "after_duplicates": 27, "screened": 27,
                                 "included_studies": None})  # fmt: skip
    assert [(g.box, g.published, g.tool, g.difference) for g in gaps] == [
        ("identified", 30, 29, -1),
        ("after_duplicates", 27, 27, 0),
    ]
    assert gaps[0].relative == pytest.approx(-1 / 30)
    zero = flow_gaps(PublishedFlow(screened=0), {"screened": 2})
    assert zero[0].relative is None


def test_screening_loss_descriptors() -> None:
    without, by_criterion = screening_loss_descriptors(
        [(False, "C1"), (True, "P1"), (True, "C1"), (True, None)]
    )
    assert without == 1
    assert by_criterion == {"C1": 2, "": 1, "P1": 1}


def test_year_descriptors() -> None:
    assert year_descriptors([2022, 2026, None, 2025], 2025) == {
        "within": 2, "after": 1, "unknown": 1
    }  # fmt: skip
    assert year_descriptors([2022], None) == {"within": 0, "after": 0, "unknown": 1}
