"""Replay a published review with the tool alone (``banc-replication``, D-103, D-104).

The benchmark creates a project marked ``replication`` in the review folder, one per
mode (``replication-par-etape.revue``, ``replication-en-chaine.revue``), then chains
the steps with the use cases of the tool, without duplicating their logic:

1. search: the RIS exports of ``recherche/`` (``collect.imports``) and, when given, the
   rebuilt strategy collected in PubMed or OpenAlex (``search.strategies``,
   ``collect.collection``);
2. deduplication (``collect.deduplication``, rules of D-062); pairs left to a person
   stay apart;
3. title and abstract screening by the AI in batches (``screening.batch_ai``), its
   decisions final (D-104); chained mode only, the screening being the same in both
   modes (docs/11 §3);
4. retrieval of the full texts: open access, then the PDFs of ``textes/``. The run
   stops here while texts are missing, with their list; it resumes when run again;
5. full-text screening by the AI in batches;
6. reports of a same study: the AI's verdict on each pair proposed is final;
7. extraction by the AI (``extraction.prefill``);
8. narrative synthesis by the AI, field by field (produced, not compared, docs/11 §7);
9. flow diagram, marked « Simulation de réplication ».

Replayed stepwise, steps 4 to 8 get the included studies of the published review,
imported from ``norme/incluses.csv`` as references of provenance ``reference_standard``.

The cost of each AI step is shown before it (``preview``) and confirmed; the ceiling
is the project budget, checked before each call, retries included (D-069). Running the
command again resumes where it stopped (D-059), without paying again what is done:
the calls already recorded and the batches already sent are kept (D-080).
"""

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import JsonValue

from revue_portee.ai.providers import ProviderFactory
from revue_portee.collect import collection as collection_uc
from revue_portee.collect.deduplication import dedup_state, run_deduplication
from revue_portee.collect.imports import AlreadyImportedError, import_ris
from revue_portee.dedup.standard import match_studies
from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.dedup import DedupSettings
from revue_portee.domain.framing import Framing
from revue_portee.domain.fulltext import RetrievalStatus
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import ReplicationMarker, ReplicationMode
from revue_portee.domain.references import ImportFile, Provenance, Reference, SourceKind
from revue_portee.domain.screening import ScreeningMode
from revue_portee.domain.studies import LinkOutcome, LinkVerdict
from revue_portee.extraction import grid as grid_uc
from revue_portee.extraction import prefill
from revue_portee.fulltext import retrieval
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.protocol import criteria as criteria_uc
from revue_portee.protocol.ai_assist import CostPreview, default_provider_factory
from revue_portee.protocol.framing import save_framing
from revue_portee.replication.inputs import (
    STANDARD_FOLDER,
    ReplicationInputError,
    ReviewInputs,
    Standard,
)
from revue_portee.screening import batch_ai, fulltext, main, studies
from revue_portee.screening.report import export_flow
from revue_portee.screening.settings import set_budget
from revue_portee.search.strategies import save_strategy
from revue_portee.storage.project_folder import (
    ProjectFolder,
    create_project_folder,
    open_project_folder,
)
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import references as references_repo
from revue_portee.storage.repositories import screening as screening_repo
from revue_portee.synthesis import narrative

__all__ = [
    "MODE_SLUGS",
    "SEED",
    "BenchOutcome",
    "BenchSettings",
    "Stop",
    "project_path",
    "run_bench",
]

Clock = Callable[[], datetime]
Confirm = Callable[[str, CostPreview], bool]
SEED = 2026  # order of the screening rounds (it changes no decision)
MODE_SLUGS = {ReplicationMode.STEPWISE: "par-etape", ReplicationMode.CHAINED: "en-chaine"}
REVIEWER = "banc-replication"
STANDARD_SOURCE = "reference_standard"
NOT_OBTAINED = "texte non obtenu pour la réplication"


class Stop(StrEnum):
    NONE = ""  # every step done
    REFUSED = "refused"  # a cost was not confirmed
    CEILING = "ceiling"  # the next call would pass the ceiling
    TEXTS = "texts"  # full texts to upload before going on


@dataclass(frozen=True, slots=True)
class BenchSettings:
    mode: ReplicationMode
    ceiling: Decimal
    go_on_without_texts: bool = False  # declare the missing texts not retrievable
    open_access: bool = True  # look for open access texts (OpenAlex, Unpaywall)


@dataclass(frozen=True, slots=True)
class BenchOutcome:
    project: Path
    stopped: Stop
    step: str  # the step where the run stopped, or "" when complete
    missing: list[Reference] = field(default_factory=list)  # texts to upload
    spent: Decimal = Decimal(0)


def project_path(folder: Path, mode: ReplicationMode) -> Path:
    return folder / f"replication-{MODE_SLUGS[mode]}.revue"


@dataclass
class _Run:
    """One run of the benchmark: the project, its settings and its dependencies."""

    folder: ProjectFolder
    inputs: ReviewInputs
    settings: BenchSettings
    factory: ProviderFactory
    finder: Callable[[], retrieval.OpenAccessFinder] | None
    collector: collection_uc.CollectorFactory | None
    confirm: Confirm
    say: Callable[[str], None]
    now: Clock
    tool_version: str
    wait: Callable[[float], None]
    poll_seconds: float

    def spent(self) -> Decimal:
        with self.folder.engine.connect() as connection:
            return screening_repo.total_spent(connection)

    def left(self) -> Decimal:
        return self.settings.ceiling - self.spent()

    def ask(self, step: str, preview: CostPreview) -> bool:
        return preview.items == 0 or self.confirm(step, preview)


# --- Project and inputs ---------------------------------------------------------------


def _open_project(inputs: ReviewInputs, mode: ReplicationMode, *, now: Clock,
                  tool_version: str) -> ProjectFolder:  # fmt: skip
    path = project_path(inputs.folder, mode)
    marker = ReplicationMarker(review_id=inputs.sheet.id, mode=mode)
    if not path.exists():
        return create_project_folder(
            path,
            title=french("Replication of {review} ({mode})").format(
                review=inputs.sheet.id, mode=MODE_SLUGS[mode]
            ),
            language=inputs.criteria.language,
            reviewer_name=REVIEWER,
            now=now,
            tool_version=tool_version,
            replication=marker,
        )
    folder = open_project_folder(path, now=now, tool_version=tool_version)
    if folder.replication != marker:
        folder.close()
        raise ReplicationInputError(
            _("{path} is not the replication project of this review in this mode.").format(
                path=path
            )
        )
    return folder


def _set_up(run: _Run) -> None:
    """Question, criteria, grid and ceiling of the project (once; the ceiling again
    when it changes)."""
    folder, inputs, now, version = run.folder, run.inputs, run.now, run.tool_version
    if inputs.criteria.review_question.strip():
        save_framing(folder, Framing(question=inputs.criteria.review_question), now=now,
                     tool_version=version)  # fmt: skip
    if criteria_uc.criteria_state(folder).active is None:
        for c in inputs.criteria.criteria:
            criteria_uc.add_criterion(
                folder, pcc_element=PccElement(c.pcc_element), kind=CriterionKind(c.kind),
                text=c.text, guidance=c.guidance, examples=c.examples,
                counterexamples=c.counterexamples, now=now, tool_version=version,
            )  # fmt: skip
        criteria_uc.activate_draft(folder, rationale="", now=now, tool_version=version)
    if grid_uc.grid_state(folder).active is None:
        grid_uc.add_template(folder, template=inputs.grid, now=now, tool_version=version)
        grid_uc.activate_draft(folder, rationale="", now=now, tool_version=version)
    with folder.engine.connect() as connection:
        budget = screening_repo.latest_budget(connection)
    if budget is None or budget.limit_amount != run.settings.ceiling:
        set_budget(folder, run.settings.ceiling, now=now, tool_version=version)


# --- Steps 1 and 2: search and deduplication ------------------------------------------


def _search(run: _Run) -> None:
    folder, now, version = run.folder, run.now, run.tool_version
    for path in run.inputs.ris_files:
        try:
            import_ris(folder, path.name, path.read_bytes(), now=now, tool_version=version)
            run.say(_("RIS file imported: {file}").format(file=path.name))
        except AlreadyImportedError:
            pass
    plan = run.inputs.search
    if plan is None:
        return
    save_strategy(folder, plan.strategy, rationale=french("Published search strategy, rebuilt"),
                  now=now, tool_version=version)  # fmt: skip
    for database in plan.databases:
        runs = [s for s in collection_uc.collection_states(folder).values()
                if s.run.database is database]  # fmt: skip
        if any(s.finished for s in runs):
            continue
        open_runs = [s for s in runs if not s.finished]
        run_id = (
            open_runs[0].run.id
            if open_runs
            else collection_uc.start_collection(folder, database, now=now, tool_version=version).id
        )
        if run.collector is None:
            state = collection_uc.collect(folder, run_id, now=now, tool_version=version)
        else:
            state = collection_uc.collect(folder, run_id, now=now, tool_version=version,
                                          factory=run.collector)  # fmt: skip
        run.say(
            _("Collected in {database}: {count} records").format(
                database=database.display_name, count=state.collected
            )
        )


def _deduplicate(run: _Run) -> None:
    if dedup_state(run.folder).run is None:
        found = run_deduplication(run.folder, DedupSettings(), now=run.now,
                                  tool_version=run.tool_version)  # fmt: skip
        run.say(
            _("Deduplication: {references} references compared").format(
                references=found.reference_count
            )
        )


def _import_standard(run: _Run, standard: Standard) -> None:
    """Replayed stepwise: add the published included studies as references of
    provenance ``reference_standard``, each with the fields of the reference it
    matches in the collection, or those of ``incluses.csv`` (once)."""
    folder = run.folder
    with folder.engine.connect() as connection:
        done = [i for i in references_repo.list_imports(connection)
                if i.database_declared == STANDARD_SOURCE]  # fmt: skip
    if done:
        if done[0].sha256 != standard.sha256:
            raise ReplicationInputError(
                _("norme/incluses.csv changed since it was imported in this project.")
            )
        return
    dedup = dedup_state(folder)
    duplicates = {ref for group in dedup.groups for ref in group.duplicates}
    collected = [r for ref, r in dedup.references.items() if ref not in duplicates]
    match = match_studies(standard.studies, collected)
    content = (run.inputs.folder / STANDARD_FOLDER / "incluses.csv").read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    target = folder.path / "imports" / f"{sha256}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    with folder.write() as connection:
        moment = run.now()
        imported = ImportFile(
            id=new_ulid(moment), filename="incluses.csv", sha256=sha256, format="csv",
            database_declared=STANDARD_SOURCE, imported_at=moment,
            record_count=len(standard.studies), reviewer_id=folder.reviewer_id,
        )  # fmt: skip
        matched: dict[str, JsonValue] = {k: list(v) for k, v in match.by_study.items()}
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.REPLICATION_STANDARD_IMPORTED,
            subject_type="import_file",
            subject_id=imported.id,
            summary_fr=french(
                "Replication: included studies of the published review imported: {count} "
                "(matched to the collection: {matched})"
            ).format(count=len(standard.studies), matched=len(match.by_study)),
            tool_version=run.tool_version,
            payload={
                "sha256": sha256,
                "studies": len(standard.studies),
                "matched": matched,
                "unmatched": list(match.unmatched),
            },
        )
        references_repo.insert_import(connection, imported, journal_entry_id=entry.id)
        for position, study in enumerate(standard.studies, start=1):
            refs = match.references(study.study_id)
            source = dedup.references[refs[0]] if refs else None
            reference = Reference(
                id=new_ulid(moment),
                title=(source.title if source else "") or study.title or study.citation,
                abstract=source.abstract if source else "",
                authors=source.authors if source else (),
                year=source.year if source else None,
                container_title=source.container_title if source else "",
                volume=source.volume if source else "",
                issue=source.issue if source else "",
                pages=source.pages if source else "",
                doi=(source.doi if source else "") or study.doi,
                pmid=(source.pmid if source else "") or study.pmid,
                language=source.language if source else "",
                doc_type=source.doc_type if source else "",
                created_at=moment,
            )
            references_repo.insert_reference(connection, reference)
            references_repo.insert_provenance(
                connection,
                Provenance(
                    id=new_ulid(moment), reference_id=reference.id,
                    source=SourceKind.REFERENCE_STANDARD, original_id=study.study_id,
                    import_file_id=imported.id, page=position, created_at=moment,
                ),
            )  # fmt: skip
    run.say(
        _("Included studies of the published review imported: {count}").format(
            count=len(standard.studies)
        )
    )


# --- AI steps -------------------------------------------------------------------------


def _follow(run: _Run, round_id: str) -> None:
    batch_ai.follow(
        run.folder, round_id, factory=run.factory, now=run.now, tool_version=run.tool_version,
        wait=run.wait, poll_seconds=run.poll_seconds,
    )  # fmt: skip


def _batches(run: _Run, step: str, round_id: str) -> Stop:
    """Screen the members of a round in batches: collect what was sent before (never
    paid twice), then send what the AI has not decided, retries included."""
    _follow(run, round_id)
    while True:
        preview = batch_ai.preview(run.folder, round_id, factory=run.factory)
        if preview.items == 0:
            return Stop.NONE
        if not run.ask(step, preview):
            return Stop.REFUSED
        sent = batch_ai.submit(
            run.folder, round_id, batch_limit=run.left(), factory=run.factory, now=run.now,
            tool_version=run.tool_version,
        )  # fmt: skip
        _follow(run, round_id)
        if sent.stopped:
            return Stop.CEILING


def _title_abstract(run: _Run) -> Stop:
    started = main.main_round(run.folder)
    if started is None:
        started = main.start_main(run.folder, seed=SEED, now=run.now,
                                  tool_version=run.tool_version)  # fmt: skip
    return _batches(run, _("Title and abstract screening"), started.id)


def _retrieval(run: _Run) -> list[Reference]:
    """Open access texts, then the PDFs of ``textes/``; the texts still missing."""
    folder, now, version = run.folder, run.now, run.tool_version
    if run.settings.open_access and run.finder is not None:
        found = retrieval.retrieve_open_access(folder, now=now, tool_version=version,
                                               finder=run.finder)  # fmt: skip
        if found.looked_for:
            run.say(
                _("Open access: looked for {looked_for}, obtained {obtained}").format(
                    looked_for=found.looked_for, obtained=found.obtained
                )
            )
    files = run.inputs.texts
    if files:
        report = retrieval.upload_files(
            folder, ((p.name, p.read_bytes()) for p in files), now=now, tool_version=version
        )
        if report.added:
            run.say(_("Texts added from textes/: {count}").format(count=len(report.added)))
    waiting = (RetrievalStatus.NOT_SOUGHT, RetrievalStatus.NOT_FOUND)
    missing = [r.reference for r in retrieval.retrieval_report(folder).rows if r.status in waiting]
    if missing and run.settings.go_on_without_texts:
        for reference in missing:
            retrieval.declare_not_retrievable(folder, reference.id, NOT_OBTAINED, now=now,
                                              tool_version=version)  # fmt: skip
        return []
    return missing


def _full_text(run: _Run) -> Stop:
    folder = run.folder
    if fulltext.main_round(folder) is None:
        if not fulltext.screenable_texts(folder):
            return Stop.NONE  # no text obtained: nothing goes on
        fulltext.start_main(folder, ScreeningMode.BLIND, seed=SEED, now=run.now,
                            tool_version=run.tool_version)  # fmt: skip
    else:
        fulltext.add_new_texts(folder, now=run.now, tool_version=run.tool_version)
    main_round = fulltext.main_round(folder)
    assert main_round is not None  # noqa: S101 - started above
    return _batches(run, _("Full-text screening"), main_round.id)


def _reports(run: _Run) -> Stop:
    """The AI examines the pairs of reports proposed; its verdict is final: one study
    when it says so, two otherwise (an uncertain verdict keeps the reports apart)."""
    folder = run.folder
    preview = studies.preview_ai(folder, factory=run.factory)
    if not run.ask(_("Reports of a same study"), preview):
        return Stop.REFUSED
    if preview.items:
        result = studies.run_ai(folder, batch_limit=run.left(), factory=run.factory,
                                now=run.now, tool_version=run.tool_version)  # fmt: skip
        if result.stopped:
            return Stop.CEILING
    state = studies.study_state(folder)
    for pair, assessment in sorted(state.assessments.items()):
        if pair in state.decisions or not {*pair} <= set(state.reports):
            continue
        same = assessment.verdict is LinkVerdict.SAME
        studies.decide(
            folder, pair[0], pair[1], LinkOutcome.SAME if same else LinkOutcome.DIFFERENT,
            note=french("Replication: verdict of the AI ({verdict})").format(
                verdict=assessment.verdict.value
            ),
            reviewer_id=assessment.reviewer_id, now=run.now, tool_version=run.tool_version,
        )  # fmt: skip
    return Stop.NONE


def _extraction(run: _Run) -> Stop:
    preview = prefill.preview_ai(run.folder, factory=run.factory)
    if not run.ask(_("Extraction"), preview):
        return Stop.REFUSED
    if preview.items:
        result = prefill.run_ai(run.folder, batch_limit=run.left(), factory=run.factory,
                                now=run.now, tool_version=run.tool_version)  # fmt: skip
        if result.stopped:
            return Stop.CEILING
    return Stop.NONE


def _synthesis(run: _Run) -> Stop:
    """A narrative draft of each field with values (produced, not compared)."""
    for item in narrative.narrative_state(run.folder).fields:
        if item.current is not None or not item.studies:
            continue
        code = item.field.code
        preview = narrative.preview_ai(run.folder, code, factory=run.factory)
        if not run.ask(_("Narrative synthesis of {field}").format(field=code), preview):
            return Stop.REFUSED
        try:
            narrative.draft_with_ai(run.folder, code, ceiling=run.left(), factory=run.factory,
                                    now=run.now, tool_version=run.tool_version)  # fmt: skip
        except narrative.CeilingReachedError:
            return Stop.CEILING
        except narrative.DraftFailedError:
            continue  # recorded in the journal, counted with the unusable answers
    return Stop.NONE


# --- The run --------------------------------------------------------------------------


def _end(run: _Run, stopped: Stop, step: str) -> BenchOutcome:
    spent = run.spent()
    with run.folder.write() as connection:
        journal.append_entry(
            connection,
            now=run.now(),
            actor_reviewer_id=run.folder.reviewer_id,
            entry_type=EntryType.REPLICATION_RUN_ENDED,
            subject_type="project",
            subject_id=run.folder.project_id,
            summary_fr=(
                french("Replication: every step done")
                if stopped is Stop.NONE
                else french("Replication: stopped at the step « {step} » ({reason})").format(
                    step=step, reason=stopped.value
                )
            ),
            tool_version=run.tool_version,
            payload={
                "mode": run.settings.mode.value,
                "completed": stopped is Stop.NONE,
                "stopped": stopped.value,
                "step": step,
                "ceiling": str(run.settings.ceiling),
                "spent": str(spent),
            },
        )
    return BenchOutcome(project=run.folder.path, stopped=stopped, step=step, spent=spent)


def run_bench(
    inputs: ReviewInputs,
    settings: BenchSettings,
    *,
    standard: Standard | None = None,
    factory: ProviderFactory = default_provider_factory,
    finder: Callable[[], retrieval.OpenAccessFinder] | None = None,
    collector: collection_uc.CollectorFactory | None = None,
    confirm: Confirm,
    say: Callable[[str], None] = lambda _message: None,
    now: Clock,
    tool_version: str,
    wait: Callable[[float], None] = time.sleep,
    poll_seconds: float = batch_ai.POLL_SECONDS,
) -> BenchOutcome:
    """Run (or resume) the replay of a review in ``settings.mode``. Replayed stepwise,
    ``standard`` gives the included studies of the published review."""
    if settings.mode is ReplicationMode.STEPWISE and standard is None:
        raise ReplicationInputError(_("Replayed stepwise, the reference standard is needed."))
    folder = _open_project(inputs, settings.mode, now=now, tool_version=tool_version)
    run = _Run(
        folder=folder, inputs=inputs, settings=settings, factory=factory, finder=finder,
        collector=collector, confirm=confirm, say=say, now=now, tool_version=tool_version,
        wait=wait,
        poll_seconds=poll_seconds,
    )  # fmt: skip
    try:
        _set_up(run)
        _search(run)
        _deduplicate(run)
        if settings.mode is ReplicationMode.STEPWISE:
            assert standard is not None  # noqa: S101 - checked above
            _import_standard(run, standard)
        else:
            stopped = _title_abstract(run)
            if stopped is not Stop.NONE:
                return _end(run, stopped, _("Title and abstract screening"))
        missing = _retrieval(run)
        if missing:
            outcome = _end(run, Stop.TEXTS, _("Retrieval of the full texts"))
            return BenchOutcome(
                project=outcome.project, stopped=outcome.stopped, step=outcome.step,
                missing=missing, spent=outcome.spent,
            )  # fmt: skip
        for step, action in (
            (_("Full-text screening"), _full_text),
            (_("Reports of a same study"), _reports),
            (_("Extraction"), _extraction),
            (_("Narrative synthesis"), _synthesis),
        ):
            stopped = action(run)
            if stopped is not Stop.NONE:
                return _end(run, stopped, step)
        export_flow(folder, language="fr", now=now, tool_version=tool_version)
        return _end(run, Stop.NONE, "")
    finally:
        folder.close()
