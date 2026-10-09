"""Draft methods section on the AI in title and abstract screening, from the project
(EF-DEC-03, ENF-LAN-04).

Everything is read from the data: the model calls and the exact model versions they
returned, the pilot round the thresholds were set after, the thresholds, the main
screening, its reconciliations and reassessments, and the cost of each phase. The
section is written in ``exports/`` as ``methode-<langue>.md`` and ``.docx``.
"""

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from revue_portee.ai.tasks.fulltext import SCREEN_FULLTEXT
from revue_portee.ai.tasks.screening import SCREEN_REFERENCE
from revue_portee.domain.fulltext import QuoteCheck
from revue_portee.domain.project import ReviewerKind as PersonKind
from revue_portee.domain.screening import RoundKind, keeps, page_quote_counts, quote_counts
from revue_portee.protocol.document import ExportFormat
from revue_portee.reporting.document import Document, render_docx, render_markdown
from revue_portee.reporting.methods import (
    ChangeSummary,
    CostLine,
    ExtractionSummary,
    FieldAgreementLine,
    FulltextSummary,
    MethodsData,
    ModelUse,
    PilotSummary,
    ScreeningSummary,
    ThresholdSummary,
    build_methods,
)
from revue_portee.resources import price_table, tool_validation
from revue_portee.screening import fulltext, main, pilot, reassessment, settings, studies
from revue_portee.screening.report import flow_report, full_text_counts
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import projects
from revue_portee.storage.repositories import screening as screening_repo
from revue_portee.storage.repositories.ai import StoredCall

__all__ = ["export_methods", "methods_data", "methods_document"]

Clock = Callable[[], datetime]
TASK = SCREEN_REFERENCE.name


def _models(calls: list[StoredCall]) -> tuple[ModelUse, ...]:
    answered: dict[tuple[str, str, str], list[datetime]] = defaultdict(list)
    for call in calls:
        record = call.record
        if record.status == "ok" and record.model_returned:
            key = (record.provider, record.model_requested, record.model_returned)
            answered[key].append(record.created_at)
    return tuple(
        ModelUse(
            provider=provider,
            model_requested=requested,
            model_returned=returned,
            calls=len(moments),
            first=min(moments),
            last=max(moments),
        )
        for (provider, requested, returned), moments in sorted(answered.items())
    )


def _pilot_summary(folder: ProjectFolder, based_on: str | None) -> PilotSummary | None:
    rounds = pilot.list_rounds(folder)
    if not rounds:
        return None
    chosen = next((r for r in rounds if r.id == based_on), rounds[-1])
    state = pilot.pilot_state(folder, chosen.id)
    metrics = state.metrics
    compared = sum(1 for ref in chosen.reference_ids if ref in state.human and ref in state.ai)
    calibration = state.calibration
    return PilotSummary(
        number=chosen.number,
        sample_size=chosen.sample_size,
        seed=chosen.seed,
        criteria_version=state.criteria.number,
        compared=compared,
        agreement=None if metrics is None else metrics.agreement,
        kappa=None if metrics is None else metrics.kappa,
        ac1=None if metrics is None else metrics.ac1,
        sensitivity=None if metrics is None else metrics.sensitivity,
        sensitivity_interval=None if metrics is None else metrics.sensitivity_interval,
        specificity=None if metrics is None else metrics.specificity,
        specificity_interval=None if metrics is None else metrics.specificity_interval,
        true_positives=0 if metrics is None else metrics.confusion.tp,
        false_positives=0 if metrics is None else metrics.confusion.fp,
        false_negatives=0 if metrics is None else metrics.confusion.fn,
        true_negatives=0 if metrics is None else metrics.confusion.tn,
        calibration_method=None if calibration is None else calibration.calibration.method,
        calibration_fitted_on=0 if calibration is None else calibration.calibration.fitted_on,
        rounds=len(rounds),
    )


def _fulltext_pilot(folder: ProjectFolder) -> PilotSummary | None:
    trial = fulltext.pilot_round(folder)
    if trial is None:
        return None
    state = fulltext.pilot_state(folder, trial.id)
    metrics = state.metrics
    with folder.engine.connect() as connection:
        version = criteria_repo.get_version(connection, trial.criteria_version_id)
        rounds = screening_repo.list_rounds(connection, fulltext.STAGE)
    return PilotSummary(
        number=trial.number,
        sample_size=trial.sample_size,
        seed=trial.seed,
        criteria_version=0 if version is None else version.number,
        compared=sum(1 for r in trial.reference_ids if r in state.human and r in state.ai),
        agreement=None if metrics is None else metrics.agreement,
        kappa=None if metrics is None else metrics.kappa,
        ac1=None if metrics is None else metrics.ac1,
        sensitivity=None if metrics is None else metrics.sensitivity,
        sensitivity_interval=None if metrics is None else metrics.sensitivity_interval,
        specificity=None if metrics is None else metrics.specificity,
        specificity_interval=None if metrics is None else metrics.specificity_interval,
        true_positives=0 if metrics is None else metrics.confusion.tp,
        false_positives=0 if metrics is None else metrics.confusion.fp,
        false_negatives=0 if metrics is None else metrics.confusion.fn,
        true_negatives=0 if metrics is None else metrics.confusion.tn,
        rounds=len(rounds),
    )


def _fulltext(folder: ProjectFolder, calls: list[StoredCall]) -> FulltextSummary | None:
    """The full-text screening, once its main round has started."""
    if fulltext.main_round(folder) is None:
        return None
    state = fulltext.main_state(folder)
    config = folder.ai_settings().tasks.get(SCREEN_FULLTEXT.name)
    thresholds = fulltext.fulltext_thresholds(folder)
    members = set(state.members)
    reconciled = [r for r in state.disagreements if r in state.reconciled]
    checks = page_quote_counts(a for r in members if r in state.ai for a in state.ai[r].assessments)
    followed, compared = state.followed_ai
    grouped = studies.study_state(folder)
    reassessments = [
        reassessment.reassessment_state(folder, i.id)
        for i in reassessment.impacts(folder, state.round.id)
        if i.reassessment_round_id is not None
    ]
    versions = sorted(
        {c.record.prompt_template_version for c in calls if c.task == SCREEN_FULLTEXT.name}
    )
    return FulltextSummary(
        mode=state.round.mode.value,
        provider="" if config is None else str(config.provider or ""),
        model="" if config is None else str(config.model or ""),
        template_version=", ".join(versions) or SCREEN_FULLTEXT.version,
        exclude_below=thresholds.exclude_below,
        include_above=thresholds.include_above,
        pilot=_fulltext_pilot(folder),
        texts=len(members),
        by_person=len(members & state.human.keys()),
        by_ai=len(members & state.ai.keys()),
        unreadable=len(state.unreadable),
        disagreements=len(state.disagreements),
        reconciled=len(reconciled),
        reconciled_with_ai=sum(
            1 for r in reconciled if keeps(state.reconciled[r].value) == keeps(state.ai[r].value)
        ),
        followed_ai=followed,
        assisted_compared=compared,
        quotes_at_page=checks[QuoteCheck.AT_PAGE],
        quotes_other_page=checks[QuoteCheck.OTHER_PAGE],
        quotes_not_found=checks[QuoteCheck.NOT_FOUND],
        study_pairs=len(grouped.candidates),
        study_pairs_ai=sum(
            1
            for c in grouped.candidates
            if (c.reference_a_id, c.reference_b_id) in grouped.assessments
        ),
        study_pairs_decided=len(grouped.decisions),
        studies=len(grouped.studies),
        included_reports=len(grouped.reports),
        changes=len(reassessment.impacts(folder, state.round.id)),
        reassessed=sum(len(r.members) for r in reassessments),
        changed=sum(
            1
            for r in reassessments
            for ref, d in r.verified.items()
            if ref in r.previous and keeps(d.value) != keeps(r.previous[ref].value)
        ),
    )


def _thresholds(folder: ProjectFolder) -> tuple[ThresholdSummary, str | None]:
    """Thresholds in force, and the pilot round they were set after."""
    thresholds, calibration = settings.thresholds_in_force(folder)
    with folder.engine.connect() as connection:
        setting = screening_repo.latest_threshold(connection, main.STAGE)
    summary = ThresholdSummary(
        exclude_below=thresholds.exclude_below,
        include_above=thresholds.include_above,
        calibrated=calibration is not None,
        set_by_person=setting is not None,
        target_sensitivity=None if setting is None else setting.target_sensitivity,
        justification="" if setting is None else setting.justification,
    )
    return summary, None if setting is None else setting.based_on_round_id


def _costs(folder: ProjectFolder, calls: list[StoredCall]) -> tuple[CostLine, ...]:
    """Cost of the screening calls by phase: a call belongs to the round of the decision
    it gave, or of the batch it was part of (a failed call gives no decision)."""
    with folder.engine.connect() as connection:
        kinds = {
            r.id: kind.value
            for kind in RoundKind
            for r in screening_repo.list_screening_rounds(connection, main.STAGE, kind)
        } | {
            r.id: f"full_text_{kind.value}"
            for kind in (RoundKind.PILOT, RoundKind.MAIN)
            for r in screening_repo.list_screening_rounds(connection, fulltext.STAGE, kind)
        }
        phase_of_call = {
            d.ai_call_id: kinds.get(d.round_id or "", "unlinked")
            for d in screening_repo.list_decisions(connection)
            if d.ai_call_id is not None
        }
        phase_of_batch = {
            b.provider_batch_id: kinds[round_id]
            for round_id in kinds
            for b in screening_repo.list_ai_batches(connection, round_id)
        }
    calls_by_phase: Counter[str] = Counter()
    amounts: defaultdict[str, Decimal] = defaultdict(Decimal)
    read: Counter[str] = Counter()
    written: Counter[str] = Counter()
    for call in calls:
        phase = phase_of_call.get(call.id) or phase_of_batch.get(call.record.batch_id or "")
        phase = phase or "unlinked"
        record = call.record
        calls_by_phase[phase] += 1
        amounts[phase] += record.cost_estimate
        read[phase] += record.input_tokens + record.cache_read_tokens + record.cache_write_tokens
        written[phase] += record.output_tokens
    return tuple(
        CostLine(
            phase=phase,
            calls=calls_by_phase[phase],
            amount=amounts[phase],
            input_tokens=read[phase],
            output_tokens=written[phase],
        )
        for phase in (RoundKind.PILOT.value, RoundKind.MAIN.value, RoundKind.REASSESSMENT.value,
                      "full_text_pilot", "full_text_main", "unlinked")
    )  # fmt: skip


def _screening(state: main.MainState) -> ScreeningSummary:
    members = set(state.members)
    both = members & state.human.keys() & state.ai.keys()
    reconciled = [ref for ref in state.disagreements if ref in state.reconciled]
    found, checked = quote_counts(
        a for ref in members if ref in state.ai for a in state.ai[ref].assessments
    )
    return ScreeningSummary(
        references=len(members),
        by_person=len(members & state.human.keys()),
        by_ai=len(members & state.ai.keys()),
        by_both=len(both),
        disagreements=len(state.disagreements),
        quotes_found=found,
        quotes_checked=checked,
        reconciled=len(reconciled),
        reconciled_with_ai=sum(
            1
            for ref in reconciled
            if keeps(state.reconciled[ref].value) == keeps(state.ai[ref].value)
        ),
    )


def _extraction(folder: ProjectFolder, calls: list[StoredCall]) -> ExtractionSummary | None:
    """The data extraction, once a grid is in force and values exist."""
    # Imported here: the extraction reads the studies, which import the screening.
    from revue_portee.ai.tasks.extraction import EXTRACT_FIELDS
    from revue_portee.ai.tasks.synthesis import DRAFT_SYNTHESIS
    from revue_portee.domain.extraction import ValueStatus, current_values, quote_summary
    from revue_portee.domain.narrative import DraftStatus
    from revue_portee.extraction import prefill, validation
    from revue_portee.storage.repositories import extraction as extraction_repo
    from revue_portee.storage.repositories import narrative as narrative_repo

    state = prefill.extraction_state(folder)
    with folder.engine.connect() as connection:
        values = extraction_repo.list_values(connection)
    if state.grid is None or not values:
        return None
    studies_ids = {s.primary.id for s in state.studies}
    codes = {f.code for f in state.grid.fields}
    in_force = [
        v
        for (ref, code), v in current_values(values).items()
        if ref in studies_ids and code in codes
    ]
    statuses = Counter(v.status for v in in_force)
    ai_values = [v for v in values if v.reviewer_kind is PersonKind.AI]
    checks = quote_summary(current_values(ai_values).values())
    config = folder.ai_settings().tasks.get(EXTRACT_FIELDS.name)
    versions = sorted(
        {c.record.prompt_template_version for c in calls if c.task == EXTRACT_FIELDS.name}
    )
    pilot_state = validation.pilot_state(folder)
    with folder.engine.connect() as connection:
        drafts = narrative_repo.list_drafts(connection)
    narrative_calls = [c for c in calls if c.task == DRAFT_SYNTHESIS.name]
    narrative_config = folder.ai_settings().tasks.get(DRAFT_SYNTHESIS.name)
    return ExtractionSummary(
        grid_version=state.grid.number,
        fields=len(state.grid.fields),
        studies=len(state.studies),
        provider="" if config is None or not ai_values else str(config.provider or ""),
        model="" if config is None or not ai_values else str(config.model or ""),
        template_version=", ".join(versions),
        ai_studies=len({v.reference_id for v in ai_values if v.reference_id in studies_ids}),
        validated=statuses[ValueStatus.VALIDATED],
        corrected=statuses[ValueStatus.CORRECTED],
        rejected=statuses[ValueStatus.REJECTED],
        extracted=statuses[ValueStatus.EXTRACTED],
        pending=statuses[ValueStatus.PROPOSED],
        quotes_at_page=checks[QuoteCheck.AT_PAGE],
        quotes_other_page=checks[QuoteCheck.OTHER_PAGE],
        quotes_not_found=checks[QuoteCheck.NOT_FOUND],
        pilot_studies=0 if pilot_state is None else len(pilot_state.pilot.reference_ids),
        pilot_seed=None if pilot_state is None else pilot_state.pilot.seed,
        narrative_model=""
        if narrative_config is None or not narrative_calls
        else str(narrative_config.model or ""),
        narrative_template_version=", ".join(
            sorted({c.record.prompt_template_version for c in narrative_calls})
        ),
        narrative_drafted=len({d.field_code for d in drafts if d.status is DraftStatus.PROPOSED}),
        narrative_revised=len({d.field_code for d in drafts if d.status is DraftStatus.REVISED}),
        pilot_agreement=()
        if pilot_state is None
        else tuple(
            FieldAgreementLine(code=a.code, label=a.label, compared=a.compared, agreed=a.agreed)
            for a in pilot_state.agreement
        ),
    )


def methods_data(folder: ProjectFolder, *, now: Clock, tool_version: str) -> MethodsData:
    report = flow_report(folder, now=now, tool_version=tool_version)
    config = folder.ai_settings().tasks.get(TASK)
    thresholds, based_on = _thresholds(folder)
    started = main.main_round(folder)
    with folder.engine.connect() as connection:
        every_call = ai_repo.list_calls(connection)
        project = projects.get_project(connection)
        reviewers = [
            r
            for r in projects.list_reviewers(connection)
            if r.kind is PersonKind.HUMAN and r.active
        ]
        versions = {v.id: v for v in criteria_repo.list_versions(connection)}
        impacts = [] if started is None else screening_repo.list_impacts(connection, started.id)
    calls = [c for c in every_call if c.task == TASK]
    screening_calls = [c for c in every_call if c.task in (TASK, SCREEN_FULLTEXT.name)]
    others = [c for c in every_call if c.task not in (TASK, SCREEN_FULLTEXT.name)]
    templates = Counter(
        (c.record.prompt_template_id, c.record.prompt_template_version) for c in calls
    )
    changes = tuple(
        ChangeSummary(
            changes=tuple((c.code, c.change_type) for c in impact.impact.changes),
            justification=versions[impact.to_version_id].rationale,
            sampled=impact.sampled,
            counts=counts,
        )
        for impact, counts in zip(impacts, report.numbers.reassessments, strict=True)
    )
    prices = price_table()
    return MethodsData(
        project_title=project.title,
        tool_version=tool_version,
        generated_at=report.context.generated_at,
        human_reviewers=len(reviewers),
        provider="" if config is None else str(config.provider or ""),
        model="" if config is None else str(config.model or ""),
        params={} if config is None else {k: str(v) for k, v in config.params.items()},
        templates=tuple((t, v, n) for (t, v), n in sorted(templates.items())),
        models=_models(calls),
        pilot=_pilot_summary(folder, based_on),
        thresholds=thresholds,
        screening=None if started is None else _screening(main.main_state(folder, started.id)),
        flow=report.numbers,
        retrieval=full_text_counts(folder),
        changes=changes,
        costs=_costs(folder, screening_calls),
        full_text=_fulltext(folder, every_call),
        extraction=_extraction(folder, every_call),
        other_costs=CostLine(
            phase="other",
            calls=len(others),
            amount=sum((c.record.cost_estimate for c in others), Decimal(0)),
        ),
        currency=prices.currency,
        prices_as_of=prices.as_of.isoformat(),
        validation=tool_validation(),
    )


def methods_document(
    folder: ProjectFolder, *, language: str, now: Clock, tool_version: str
) -> Document:
    return build_methods(
        methods_data(folder, now=now, tool_version=tool_version), language=language
    )


def export_methods(
    folder: ProjectFolder, *, language: str, format: ExportFormat, now: Clock, tool_version: str
) -> Path:
    """Write the draft methods section in ``exports/`` and return the file path."""
    document = methods_document(folder, language=language, now=now, tool_version=tool_version)
    target = folder.path / "exports" / f"methode-{language}.{format.value}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if format is ExportFormat.MARKDOWN:
        target.write_text(render_markdown(document), encoding="utf-8")
    else:
        target.write_bytes(render_docx(document))
    return target
