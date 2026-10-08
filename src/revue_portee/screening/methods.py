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

from revue_portee.ai.tasks.screening import SCREEN_REFERENCE
from revue_portee.domain.project import ReviewerKind as PersonKind
from revue_portee.domain.screening import RoundKind, keeps, quote_counts
from revue_portee.protocol.document import ExportFormat
from revue_portee.reporting.document import Document, render_docx, render_markdown
from revue_portee.reporting.methods import (
    ChangeSummary,
    CostLine,
    MethodsData,
    ModelUse,
    PilotSummary,
    ScreeningSummary,
    ThresholdSummary,
    build_methods,
)
from revue_portee.resources import price_table, tool_validation
from revue_portee.screening import main, pilot, settings
from revue_portee.screening.report import flow_report
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
                      "unlinked")
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
    others = [c for c in every_call if c.task != TASK]
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
        changes=changes,
        costs=_costs(folder, calls),
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
