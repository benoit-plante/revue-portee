"""The demonstration project (tests/fixtures/demo/README.md), built step by step.

Nine fictitious records from three databases (tests/fixtures/dedup/demo-*.ris) give
five references after deduplication. The person and a deterministic AI screen them
with criteria version 1; they disagree on one reference, which the person reconciles.
Criterion P1 is then broadened (version 2): the impact analysis touches the two
references excluded for P1, the AI screens them again and the person verifies the one
whose decision it would change. Every number of the diagram is counted by hand in the
README.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from revue_portee.ai.base import ModelProvider, TaskInput
from revue_portee.ai.providers.fake import FakeBatches, FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.ai.tasks.screening import ScreenReferenceInput
from revue_portee.collect import deduplication, imports
from revue_portee.collect.enrichment import enriched_reference
from revue_portee.domain.changes import ChangeType
from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.dedup import DedupSettings, PairOutcome
from revue_portee.domain.screening import DecisionValue, Thresholds
from revue_portee.protocol import criteria
from revue_portee.screening import ai_screening, batch_ai, main, pilot, reassessment, settings
from revue_portee.storage.project_folder import ProjectFolder
from support import TOOL_VERSION, make_clock, new_project

Clock = Callable[[], datetime]
FIXTURES = Path(__file__).parent / "fixtures" / "dedup"
FILES = (
    ("demo-psycinfo.ris", "APA PsycInfo (EBSCOhost)"),
    ("demo-cinahl.ris", "CINAHL (EBSCOhost)"),
    ("demo-pubmed.ris", "PubMed"),
)
IN, EX, UN = DecisionValue.INCLUDE, DecisionValue.EXCLUDE, DecisionValue.UNCERTAIN
# The five references after deduplication, by a word of their title.
KEYS = ("correction", "gardens", "caregivers", "loneliness", "housing")  # in this order


def key_of(title: str) -> str:
    """The key of a reference (``KEYS``), from its title."""
    lowered = title.lower()
    return next(key for key in KEYS if key in lowered)


def _assessments(p1: str, c1: str, x1: str, quote: str = "") -> list[dict[str, str]]:
    return [
        {"code": "P1", "status": p1, "evidence_quote": quote},
        {"code": "C1", "status": c1, "evidence_quote": ""},
        {"code": "X1", "status": x1, "evidence_quote": ""},
    ]


def _output(decision: str, assessments: list[dict[str, str]]) -> dict[str, Any]:
    probability = {"include": 0.9, "exclude": 0.02}[decision]
    return {
        "assessments": assessments,
        "decision": decision,
        "inclusion_probability": probability,
        "rationale": "P1, C1 et X1 évalués.",
        "decisive_criteria": ["P1"],
    }


# The AI with version 1 (older adults): it excludes the gardens study, which the person
# keeps as uncertain (the disagreement).
AI_V1 = {
    "correction": _output("exclude", _assessments("not_met", "met", "met")),
    "housing": _output("exclude", _assessments("not_met", "met", "not_met")),
    "caregivers": _output("include", _assessments("met", "met", "not_met", "older adults")),
    "gardens": _output("exclude", _assessments("not_met", "met", "not_met", "older residents")),
    "loneliness": _output("include", _assessments("met", "met", "not_met", "older adults")),
}
# The AI with version 2 (any adult): it now keeps the housing study, not the gardens one.
AI_V2 = AI_V1 | {
    "housing": _output("include", _assessments("met", "met", "not_met")),
    "gardens": _output("exclude", _assessments("met", "not_met", "not_met")),
}
# The person's independent decisions with version 1: value and criteria cited.
HUMAN_V1 = {
    "correction": (EX, ["X1"]),
    "housing": (EX, ["P1"]),
    "caregivers": (UN, []),
    "gardens": (UN, []),
    "loneliness": (IN, []),
}


def _responder(answers: dict[str, dict[str, Any]]) -> Callable[[TaskInput], dict[str, Any]]:
    def respond(item: TaskInput) -> dict[str, Any]:
        assert isinstance(item, ScreenReferenceInput)
        return answers[key_of(item.reference.title)]

    return respond


def _factory(answers: dict[str, dict[str, Any]]) -> Callable[[AITaskConfig], ModelProvider]:
    store = FakeBatches()

    def build(config: AITaskConfig) -> ModelProvider:
        return FakeProvider(
            model=str(config.model),
            model_returned="fake-model-2026-10-07",
            responder=_responder(answers),
            cost_per_call=Decimal("0.002"),
            batches=store,
        )

    return build


def _screen_with_ai(
    folder: ProjectFolder, clock: Clock, round_id: str, answers: dict[str, dict[str, Any]]
) -> None:
    chosen = _factory(answers)
    batch_ai.submit(
        folder, round_id, batch_limit=Decimal(5), factory=chosen, now=clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    batch_ai.follow(
        folder, round_id, factory=chosen, now=clock, tool_version=TOOL_VERSION, wait=lambda _: None
    )


@dataclass(slots=True)
class Demo:
    folder: ProjectFolder
    clock: Clock
    round_id: str = ""
    impact_id: str = ""

    def ids(self) -> dict[str, str]:
        """Identifier of each of the five references of the main screening, by key."""
        return self.keyed(main.main_state(self.folder, self.round_id).members)

    def keyed(self, reference_ids: Sequence[str]) -> dict[str, str]:
        """``reference_ids`` by key."""
        found = {}
        for ref in reference_ids:
            reference = enriched_reference(self.folder, ref)
            assert reference is not None
            found[key_of(reference.title)] = ref
        return found


def create(tmp_path: Path) -> Demo:
    """The project with its criteria (version 1) and the nine records imported."""
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    for element, kind, text in (
        (PccElement.POPULATION, CriterionKind.INCLUSION, "Older adults (65 and over)."),
        (PccElement.CONCEPT, CriterionKind.INCLUSION, "Housing, living conditions or care."),
        (PccElement.OTHER, CriterionKind.EXCLUSION, "Errata and corrections."),
    ):
        criteria.add_criterion(
            folder, pcc_element=element, kind=kind, text=text, now=clock, tool_version=TOOL_VERSION
        )
    criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    for name, database in FILES:
        imports.import_ris(
            folder, name, (FIXTURES / name).read_bytes(), database=database, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    return Demo(folder, clock)


def deduplicate(demo: Demo) -> None:
    """Run the deduplication, then decide the pair left to the person: duplicates."""
    folder, clock = demo.folder, demo.clock
    deduplication.run_deduplication(folder, DedupSettings(), now=clock, tool_version=TOOL_VERSION)
    (pair,) = deduplication.dedup_state(folder).pending
    deduplication.decide_pair(
        folder, pair.reference_a_id, pair.reference_b_id, PairOutcome.DUPLICATE, now=clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip


def run_pilot(demo: Demo) -> str:
    """A pilot round of the five references (seed 7): the AI, then the person, with
    version 1; calibration fitted, thresholds set after the round. Returns its id."""
    folder, clock = demo.folder, demo.clock
    round_id = pilot.start_pilot(folder, size=5, seed=7, now=clock, tool_version=TOOL_VERSION).id
    settings.set_budget(folder, Decimal(10), now=clock, tool_version=TOOL_VERSION)
    ai_screening.run_ai(
        folder, round_id, batch_limit=Decimal(5), factory=_factory(AI_V1), now=clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    for key, ref in demo.keyed(pilot.get_round(folder, round_id).reference_ids).items():
        value, cited = HUMAN_V1[key]
        pilot.record_human_decision(
            folder, round_id, ref, value, criteria_cited=cited, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    calibration = pilot.fit_round_calibration(
        folder, round_id, now=clock, tool_version=TOOL_VERSION
    )
    settings.set_thresholds(
        folder,
        Thresholds(exclude_below=0.05, include_above=0.6),
        justification="Aucune inclusion manquée sous 0,05.",
        target_sensitivity=Decimal("0.95"),
        round_id=round_id,
        calibration_id=calibration.id,
        now=clock,
        tool_version=TOOL_VERSION,
    )
    return round_id


def screen(demo: Demo, *, ai: bool = True, human: bool = True) -> None:
    """Start the main screening; the AI and the person screen every reference."""
    folder, clock = demo.folder, demo.clock
    demo.round_id = main.start_main(folder, seed=3, now=clock, tool_version=TOOL_VERSION).id
    settings.set_budget(folder, Decimal(10), now=clock, tool_version=TOOL_VERSION)
    if ai:
        _screen_with_ai(folder, clock, demo.round_id, AI_V1)
    if human:
        screen_by_hand(demo)


def screen_by_hand(demo: Demo) -> None:
    """The person's independent decisions on the five references (``HUMAN_V1``)."""
    for key, ref in demo.ids().items():
        value, cited = HUMAN_V1[key]
        main.record_decision(
            demo.folder, demo.round_id, ref, value, criteria_cited=cited, now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip


def reconcile(demo: Demo) -> None:
    """The gardens study: the person follows the AI and excludes it for P1."""
    main.reconcile(
        demo.folder, demo.round_id, demo.ids()["gardens"], EX, criteria_cited=["P1"],
        rationale="Population non précisée : aucun indice d'aînés.", now=demo.clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip


def broaden_and_reassess(demo: Demo, *, complete: bool = True) -> None:
    """Version 2 broadens P1 to any adult; the AI screens the two references excluded
    for P1 again, and the person verifies the housing study, which it would keep."""
    folder, clock = demo.folder, demo.clock
    criteria.update_criterion(
        folder, "P1", kind=CriterionKind.INCLUSION, text="Adults (18 and over).", now=clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    criteria.activate_draft(
        folder,
        rationale="Population élargie à tous les adultes.",
        qualifications={"P1": ChangeType.BROADENING},
        now=clock,
        tool_version=TOOL_VERSION,
    )
    impact = reassessment.assess(
        folder, demo.round_id, seed=4, now=clock, tool_version=TOOL_VERSION
    )
    demo.impact_id = impact.id
    assert impact.reassessment_round_id is not None
    _screen_with_ai(folder, clock, impact.reassessment_round_id, AI_V2)
    reassessment.verify(
        folder, impact.id, demo.ids()["housing"], IN, rationale="Adultes et logement.",
        now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    if complete:
        reassessment.complete(folder, impact.id, now=clock, tool_version=TOOL_VERSION)


def build(tmp_path: Path) -> Demo:
    """The whole demonstration, up to the completed reassessment."""
    demo = create(tmp_path)
    deduplicate(demo)
    screen(demo)
    reconcile(demo)
    broaden_and_reassess(demo)
    return demo
