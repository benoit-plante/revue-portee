"""Measures of a replay and its report ``replication-<id>.md`` (tranche 3.8, D-103).

The measures are read from the replication projects of the review folder (one per
mode) and from the reference standard (``norme/``); the comparisons themselves are the
pure functions of ``domain.replication``. The report holds numbers and the
configuration only: no title, abstract, URL, quote nor raw response, as the archive
(D-092). It speaks of « concordance avec la revue publiée », never of an error: the
published review is the reference by definition (docs/11 §9).
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pydantic import JsonValue

from revue_portee.collect.deduplication import dedup_state
from revue_portee.dedup.standard import match_studies
from revue_portee.domain.dedup import ALGORITHM_VERSION
from revue_portee.domain.extraction import InvalidValueError, for_synthesis, parse_value
from revue_portee.domain.fulltext import FulltextOrigin, RetrievalStatus
from revue_portee.domain.grid import FieldType, GridField, GridVersion
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import ReplicationMode
from revue_portee.domain.references import SourceKind
from revue_portee.domain.replication import (
    NOT_REPORTED,
    WITHIN_POINTS,
    CategoricalAgreement,
    DistributionGap,
    EndToEnd,
    FlowGap,
    LossStage,
    Proportion,
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
from revue_portee.domain.screening import DecisionValue, keeps, primary_reason
from revue_portee.extraction.prefill import extraction_state
from revue_portee.fulltext import retrieval
from revue_portee.i18n import gettext as _
from revue_portee.replication.bench import MODE_SLUGS, project_path
from revue_portee.replication.inputs import ReplicationInputError, ReviewSheet, Standard
from revue_portee.screening import batch_ai, fulltext, main, studies
from revue_portee.screening.report import flow_report
from revue_portee.screening.settings import thresholds_in_force
from revue_portee.storage.project_folder import ProjectFolder, open_project_folder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import extraction as extraction_repo
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import references as references_repo

__all__ = [
    "CATEGORICAL",
    "ModeMeasures",
    "TaskCost",
    "measure",
    "measure_review",
    "report_markdown",
]

Clock = Callable[[], datetime]
CATEGORICAL = frozenset(
    {FieldType.SINGLE_CHOICE, FieldType.MULTIPLE_CHOICE, FieldType.HIERARCHICAL, FieldType.BOOLEAN}
)
_STAGE_LABELS = {
    LossStage.OUT_OF_SEARCH: "hors de toute base interrogée",
    LossStage.SEARCH: "recherche (non collectée)",
    LossStage.TITLE_ABSTRACT: "tri des titres et résumés",
    LossStage.RETRIEVAL: "obtention du texte",
    LossStage.FULL_TEXT: "tri du texte intégral",
}
_FLOW_LABELS = {
    "identified": "Références identifiées",
    "after_duplicates": "Après dédoublonnage",
    "screened": "Triées (titres et résumés)",
    "full_texts_assessed": "Textes évalués",
    "included_reports": "Rapports inclus",
    "included_studies": "Études incluses",
}


@dataclass(frozen=True, slots=True)
class TaskCost:
    task: str
    calls: int
    failed: int  # calls without an answer (provider error)
    unusable: int  # answers recorded but not usable
    input_tokens: int
    output_tokens: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ModeMeasures:
    """Everything the report says of one mode."""

    mode: ReplicationMode
    completed: bool
    identified: int
    after_duplicates: int
    retrievability: Proportion  # every published study
    retrievability_in_search: Proportion  # the studies in a database searched
    unmatched: int  # published studies matched to no collected reference
    sought: int  # references whose full text was sought
    open_access: int
    uploaded: int
    not_obtained: int
    full_text_assessed: int
    full_text_kept: int  # kept by the AI (« uncertain » included) or by rule
    full_text_uncertain: int
    full_text_recall: Proportion  # published studies obtained, kept at the full text
    reports: int  # included reports
    studies: int  # included studies, after the grouping of reports
    agreement: tuple[CategoricalAgreement, ...]
    distributions: tuple[DistributionGap, ...]
    costs: tuple[TaskCost, ...]
    duration_minutes: float | None
    kept_unusable: int  # references kept because the AI gave no usable answer
    # Chained mode only
    screened: int = 0
    screened_excluded: int = 0
    screened_uncertain: int = 0
    screening_recall: Proportion | None = None  # collected published studies kept
    flow: tuple[FlowGap, ...] = ()
    end_to_end: EndToEnd | None = None
    cascade: dict[LossStage, int] = field(default_factory=dict)
    lost_without_abstract: int = 0
    lost_by_criterion: dict[str, int] = field(default_factory=dict)
    extra_years: dict[str, int] = field(default_factory=dict)
    config: dict[str, str] = field(default_factory=dict)
    unmatched_ids: tuple[str, ...] = ()  # for the console only, never in the report


# --- Helpers --------------------------------------------------------------------------


def _category(field_: GridField, value: JsonValue, reported: bool) -> str:
    if not reported:
        return NOT_REPORTED
    if value is True:
        return "oui"
    if value is False:
        return "non"
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    return str(value)


def _published_category(field_: GridField, study_id: str, raw: str) -> str:
    if not raw:
        return NOT_REPORTED
    item: JsonValue = (
        [part.strip() for part in raw.split("|")]
        if field_.type is FieldType.MULTIPLE_CHOICE
        else raw
    )
    try:
        return _category(field_, parse_value(field_, item), True)
    except InvalidValueError as error:
        raise ReplicationInputError(
            _(
                "norme/extraction-publiee.csv: the value of {field} for {study} is not among "
                "the categories of the grid."
            ).format(field=field_.code, study=study_id)
        ) from error


def _field(grid: GridVersion, name: str) -> GridField | None:
    found = grid.field(name)
    if found is None:
        found = next((f for f in grid.fields if f.label.casefold() == name.casefold()), None)
    return found


def _completed(folder: ProjectFolder) -> bool:
    with folder.engine.connect() as connection:
        ended = [e for e in journal.list_entries(connection)
                 if e.entry_type == EntryType.REPLICATION_RUN_ENDED]  # fmt: skip
    return bool(ended) and ended[-1].payload.get("completed") is True


def _costs(folder: ProjectFolder) -> tuple[tuple[TaskCost, ...], float | None]:
    with folder.engine.connect() as connection:
        calls = ai_repo.list_calls(connection)
        unusable = {
            e.subject_id
            for e in journal.list_entries(connection)
            if e.entry_type == EntryType.AI_RESULT_UNUSABLE
        }
    by_task = defaultdict(list)
    for call in calls:
        by_task[call.task].append(call)
    costs = tuple(
        TaskCost(
            task=task,
            calls=len(items),
            failed=sum(1 for c in items if c.record.status != "ok"),
            unusable=sum(1 for c in items if c.id in unusable),
            input_tokens=sum(c.record.input_tokens for c in items),
            output_tokens=sum(c.record.output_tokens for c in items),
            amount=sum((c.record.cost_estimate for c in items), Decimal(0)),
        )
        for task, items in sorted(by_task.items())
    )
    moments = [c.record.created_at for c in calls]
    duration = (max(moments) - min(moments)).total_seconds() / 60 if moments else None
    return costs, duration


def _config(folder: ProjectFolder) -> dict[str, str]:
    """Models, prompt templates and thresholds the replay used (no raw response)."""
    with folder.engine.connect() as connection:
        calls = ai_repo.list_calls(connection)
    found: dict[str, str] = {}
    for call in calls:
        record = call.record
        found[call.task] = (
            f"{record.provider} · {record.model_requested} → {record.model_returned or '—'} · "
            f"gabarit {record.prompt_template_id} v{record.prompt_template_version}"
        )
    thresholds, calibration = thresholds_in_force(folder)
    found["seuils"] = (
        f"exclure sous {thresholds.exclude_below}, inclure à partir de "
        f"{thresholds.include_above}" + ("" if calibration is None else " (étalonnés)")
    )
    found["dédoublonnage"] = f"règles version {ALGORITHM_VERSION}"
    return dict(sorted(found.items()))


# --- Measures -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Tool:
    """The studies of the tool and the values the AI extracted for them."""

    grid: GridVersion | None
    studies: list[studies.Study]
    values: dict[tuple[str, str], tuple[JsonValue, bool]]  # (primary, field): value, reported


def _tool(folder: ProjectFolder) -> _Tool:
    grid = extraction_state(folder).grid
    with folder.engine.connect() as connection:
        kept = for_synthesis(extraction_repo.list_values(connection), replication=True)
    return _Tool(
        grid=grid,
        studies=studies.study_state(folder).studies,
        values={key: (v.value, v.reported) for key, v in kept.items()},
    )


def _agreement(
    tool: _Tool, standard: Standard, study_of: Mapping[str, studies.Study]
) -> tuple[CategoricalAgreement, ...]:
    if tool.grid is None:
        return ()
    pairs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in standard.values:
        field_ = _field(tool.grid, row.field)
        study = study_of.get(row.study_id)
        if field_ is None or field_.type not in CATEGORICAL or study is None:
            continue
        value = tool.values.get((study.primary, field_.code))
        if value is None:
            continue  # not extracted (text not readable, ceiling)
        pairs[field_.code].append(
            (_published_category(field_, row.study_id, row.value), _category(field_, *value))
        )
    return tuple(
        categorical_agreement(code, found)
        for code, found in sorted(pairs.items(), key=lambda kv: (len(kv[0]), kv[0]))
    )


def _distributions(tool: _Tool, standard: Standard) -> tuple[DistributionGap, ...]:
    if tool.grid is None:
        return ()
    found = []
    for published in standard.distributions:
        field_ = _field(tool.grid, published.field)
        if field_ is None:
            raise ReplicationInputError(
                _("norme/resultats-publies.yaml: unknown field of the grid: {field}.").format(
                    field=published.field
                )
            )
        counts: Counter[str] = Counter()
        studied = 0
        for study in tool.studies:
            value = tool.values.get((study.primary, field_.code))
            if value is None or not value[1]:
                continue
            studied += 1
            raw = value[0]
            categories = raw if isinstance(raw, list) else [raw]
            counts.update(_category(field_, item, True) for item in categories)
        found.append(
            distribution_gap(
                published.model_copy(update={"field": field_.code}), dict(counts), studied
            )
        )
    return tuple(found)


def _retrieval_counts(folder: ProjectFolder) -> tuple[int, int, int, int, set[str]]:
    rows = retrieval.retrieval_report(folder).rows
    obtained = {r.reference.id for r in rows if r.document is not None}
    open_access = sum(
        1 for r in rows if r.document is not None and r.document.origin is not FulltextOrigin.UPLOAD
    )
    uploaded = sum(
        1 for r in rows if r.document is not None and r.document.origin is FulltextOrigin.UPLOAD
    )
    not_obtained = sum(1 for r in rows if r.status is not RetrievalStatus.OBTAINED)
    return len(rows), open_access, uploaded, not_obtained, obtained


def _full_text(folder: ProjectFolder) -> tuple[int, set[str], int, set[str]]:
    """Texts assessed, texts kept (by the AI or by rule), uncertain, kept by rule."""
    if fulltext.main_round(folder) is None:
        return 0, set(), 0, set()
    state = fulltext.main_state(folder)
    by_rule = set(batch_ai.exhausted(folder, state.round.id)) | set(state.unreadable)
    kept = {r for r in state.members if r in state.final and keeps(state.final[r].value)}
    uncertain = sum(
        1 for r in state.members
        if r in state.final and state.final[r].value is DecisionValue.UNCERTAIN
    )  # fmt: skip
    return len(state.members), kept | (by_rule - set(state.final)), uncertain, by_rule


def measure(
    folder: ProjectFolder, sheet: ReviewSheet, standard: Standard, *, now: Clock
) -> ModeMeasures:
    """The measures of one replication project against the reference standard."""
    marker = folder.replication
    if marker is None:
        raise ReplicationInputError(_("This project is not a replication project."))
    chained = marker.mode is ReplicationMode.CHAINED
    dedup = dedup_state(folder)
    with folder.engine.connect() as connection:
        given = {
            p.original_id: p.reference_id
            for p in references_repo.list_provenance(connection)
            if p.source is SourceKind.REFERENCE_STANDARD
        }
    collected = {ref: r for ref, r in dedup.references.items() if ref not in given.values()}
    primary_of = {m: g.primary for g in dedup.groups for m in g.members}
    duplicates = {m for g in dedup.groups for m in g.duplicates}
    after = [ref for ref in collected if ref not in duplicates]
    match = match_studies(standard.studies, list(collected.values()))
    found_refs = {
        s.study_id: {primary_of.get(ref, ref) for ref in match.references(s.study_id)}
        for s in standard.studies
    }
    in_search = [s for s in standard.studies if s.in_search]
    retrievable = [s.study_id for s in standard.studies if s.in_search or found_refs[s.study_id]]
    # The references that stand for each published study in this project.
    refs_of: dict[str, set[str]] = (
        found_refs if chained else {sid: {ref} for sid, ref in given.items()}
    )
    sought, open_access, uploaded, not_obtained, obtained = _retrieval_counts(folder)
    assessed, kept_ft, uncertain_ft, by_rule_ft = _full_text(folder)
    tool = _tool(folder)
    matches = {
        study.primary: frozenset(sid for sid, refs in refs_of.items() if refs & set(study.reports))
        for study in tool.studies
    }
    study_of: dict[str, studies.Study] = {}
    for study in sorted(tool.studies, key=lambda s: s.primary):
        for sid in matches[study.primary]:
            study_of.setdefault(sid, study)
    included = {ref for study in tool.studies for ref in study.reports}
    published_obtained = [sid for sid, refs in refs_of.items() if refs & obtained]
    costs, duration = _costs(folder)
    measures = ModeMeasures(
        mode=marker.mode,
        completed=_completed(folder),
        identified=len(collected),
        after_duplicates=len(after),
        retrievability=Proportion(
            sum(1 for s in standard.studies if found_refs[s.study_id]), len(standard.studies)
        ),
        retrievability_in_search=Proportion(
            sum(1 for s in in_search if found_refs[s.study_id]), len(in_search)
        ),
        unmatched=len(match.unmatched),
        unmatched_ids=match.unmatched,
        sought=sought,
        open_access=open_access,
        uploaded=uploaded,
        not_obtained=not_obtained,
        full_text_assessed=assessed,
        full_text_kept=len(kept_ft),
        full_text_uncertain=uncertain_ft,
        full_text_recall=Proportion(
            sum(1 for sid in published_obtained if refs_of[sid] & kept_ft), len(published_obtained)
        ),
        reports=len(included),
        studies=len(tool.studies),
        agreement=_agreement(tool, standard, study_of),
        distributions=_distributions(tool, standard),
        costs=costs,
        duration_minutes=duration,
        kept_unusable=len(by_rule_ft),
        config=_config(folder),
    )
    if not chained:
        return measures
    return _chained(folder, measures, sheet, standard, found_refs, retrievable, matches,
                    obtained, included, tool, now)  # fmt: skip


def _chained(
    folder: ProjectFolder,
    measures: ModeMeasures,
    sheet: ReviewSheet,
    standard: Standard,
    found_refs: dict[str, set[str]],
    retrievable: list[str],
    matches: dict[str, frozenset[str]],
    obtained: set[str],
    included: set[str],
    tool: _Tool,
    now: Clock,
) -> ModeMeasures:
    started = main.main_round(folder)
    final = {} if started is None else main.main_state(folder, started.id).final
    exhausted = set() if started is None else set(batch_ai.exhausted(folder, started.id))
    kept_ta = {r for r, d in final.items() if keeps(d.value)} | exhausted
    paths = {
        s.study_id: StudyPath(
            in_search=s.in_search,
            collected=bool(found_refs[s.study_id]),
            kept=bool(found_refs[s.study_id] & kept_ta),
            obtained=bool(found_refs[s.study_id] & obtained),
            included=bool(found_refs[s.study_id] & included),
        )
        for s in standard.studies
    }
    collected_published = [sid for sid, p in paths.items() if p.collected]
    numbers = flow_report(folder, now=now, tool_version="").numbers
    tool_flow: dict[str, int | None] = {
        "identified": numbers.identified,
        "after_duplicates": numbers.identified - numbers.duplicates_removed,
        "screened": numbers.screened + len(exhausted),
        "full_texts_assessed": measures.full_text_assessed,
        "included_reports": measures.reports,
        "included_studies": measures.studies,
    }
    order = (
        []
        if started is None
        else [c.code for c in fulltext.criteria_of_round(folder, started).criteria]
    )
    lost = []
    references = dedup_state(folder).references
    for sid, path in paths.items():
        if lost_at(path) is not LossStage.TITLE_ABSTRACT:
            continue
        refs = sorted(found_refs[sid])
        excluded = [final[r] for r in refs if r in final]
        cited = primary_reason(excluded[0].criteria_cited, order) if excluded else None
        lost.append((any(references[r].abstract.strip() for r in refs), cited))
    without_abstract, by_criterion = screening_loss_descriptors(lost)
    extra = [references[s.primary].year for s in tool.studies if not matches[s.primary]]
    return replace(
        measures,
        screened=len(final) + len(exhausted),
        screened_excluded=sum(1 for d in final.values() if not keeps(d.value)),
        screened_uncertain=sum(1 for d in final.values() if d.value is DecisionValue.UNCERTAIN),
        kept_unusable=measures.kept_unusable + len(exhausted),
        screening_recall=Proportion(
            sum(1 for sid in collected_published if paths[sid].kept), len(collected_published)
        ),
        flow=tuple(flow_gaps(standard.flow, tool_flow)),
        end_to_end=end_to_end(
            [s.study_id for s in standard.studies], retrievable, list(matches.values())
        ),
        cascade=loss_cascade(paths.values()),
        lost_without_abstract=without_abstract,
        lost_by_criterion=by_criterion,
        extra_years=year_descriptors(extra, sheet.search_end),
    )


def measure_review(
    base: Path, sheet: ReviewSheet, standard: Standard, *, now: Clock, tool_version: str
) -> list[ModeMeasures]:
    """The measures of every replication project of a review folder (read only)."""
    found = []
    for mode in (ReplicationMode.CHAINED, ReplicationMode.STEPWISE):
        path = project_path(base, mode)
        if not path.exists():
            continue
        project = open_project_folder(path, now=now, tool_version=tool_version,
                                      record_opening=False)  # fmt: skip
        try:
            found.append(measure(project, sheet, standard, now=now))
        finally:
            project.close()
    return found


# --- Markdown -------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}".replace(".", ",")


def _num(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}".replace(".", ",")


def _prop(p: Proportion | None) -> str:
    if p is None:
        return "—"
    interval = p.interval
    bounds = "" if interval is None else f" [{_pct(interval[0])} à {_pct(interval[1])}]"
    return f"{p.count}/{p.total} ({_pct(p.value)}){bounds}"


def _section(m: ModeMeasures) -> list[str]:
    title = "Mode en chaîne" if m.mode is ReplicationMode.CHAINED else "Mode par étape"
    lines = [f"## {title} ({MODE_SLUGS[m.mode]})", ""]
    if not m.completed:
        lines += ["**Exécution non terminée** : nombres partiels.", ""]
    lines += [
        "### Étapes 1 et 2 — recherche et dédoublonnage",
        "",
        f"- Références reconstituées : {m.identified}; après dédoublonnage : {m.after_duplicates}",
        f"- Retrouvabilité (études incluses publiées présentes dans l'ensemble collecté) : "
        f"{_prop(m.retrievability)}",
        f"- Retrouvabilité parmi les études d'une base interrogée : "
        f"{_prop(m.retrievability_in_search)}",
        f"- Études de la norme sans référence appariée : {m.unmatched}",
        "",
    ]
    if m.mode is ReplicationMode.CHAINED:
        avoided = Proportion(m.screened_excluded, m.screened)
        lines += [
            "### Étape 3 — tri des titres et résumés",
            "",
            f"- Références triées par l'IA : {m.screened}",
            f"- Exclues par l'IA (charge évitée) : {_prop(avoided)}",
            f"- « Incertaines » (conservées) : {m.screened_uncertain}",
            f"- Rappel par rapport à la revue publiée (études incluses publiées collectées et "
            f"conservées) : {_prop(m.screening_recall)}",
            "",
        ]
    lines += [
        "### Étape 4 — obtention des textes",
        "",
        f"- Textes cherchés : {m.sought}; obtenus en libre accès : {m.open_access}; "
        f"téléversés : {m.uploaded}; non obtenus : {m.not_obtained}",
        "",
        "### Étape 5 — tri du texte intégral",
        "",
        f"- Textes évalués : {m.full_text_assessed}; conservés : {m.full_text_kept} "
        f"(dont « incertains » : {m.full_text_uncertain})",
        f"- Rappel par rapport à la revue publiée (études incluses publiées dont le texte est "
        f"obtenu, conservées) : {_prop(m.full_text_recall)}",
        "",
        "### Étape 6 — rapports d'une même étude",
        "",
        f"- Rapports inclus : {m.reports}; études après regroupement : {m.studies}",
        "",
        "### Étape 7 — extraction (champs catégoriels)",
        "",
    ]
    if m.agreement:
        lines += [
            "| Champ | Comparées | Accord | Kappa de Cohen | AC1 de Gwet | « Non rapporté » "
            "(publiée / outil) |",
            "|---|---|---|---|---|---|",
            *(
                f"| {a.field} | {a.compared} | {_prop(a.agreement)} | {_num(a.kappa)} | "
                f"{_num(a.ac1)} | {a.not_reported_published} / {a.not_reported_tool} |"
                for a in m.agreement
            ),
            "",
        ]
    else:
        lines += ["Aucun champ catégoriel comparé.", ""]
    lines += ["### Étape 8 — synthèse (répartitions publiées)", ""]
    for d in m.distributions:
        lines += [
            f"**{d.field}** — publiée : {d.published_n} études; outil : {d.tool_n} études; "
            f"catégories à moins de {WITHIN_POINTS:g} points : {_prop(d.within)}; même "
            f"catégorie modale : {'oui' if d.same_mode else 'non'}; corrélation de rang : "
            f"{_num(d.rank_correlation)}",
            "",
            "| Catégorie | Publiée (%) | Outil (%) | Écart (points) |",
            "|---|---|---|---|",
            *(
                f"| {c.category} | {_num(c.published, 1)} | {_num(c.tool, 1)} | {_num(c.gap, 1)} |"
                for c in d.categories
            ),
            "",
        ]
    if not m.distributions:
        lines += ["Aucune répartition publiée comparée.", ""]
    if m.mode is ReplicationMode.CHAINED:
        lines += _chained_section(m)
    lines += [
        "### Coûts et appels",
        "",
        "| Tâche | Appels | Appels en échec | Réponses inutilisables | Jetons (entrée / sortie) "
        "| Coût estimé (USD) |",
        "|---|---|---|---|---|---|",
        *(
            f"| {c.task} | {c.calls} | {c.failed} | {c.unusable} | {c.input_tokens} / "
            f"{c.output_tokens} | {c.amount} |"
            for c in m.costs
        ),
        f"| **Total** | {sum(c.calls for c in m.costs)} | {sum(c.failed for c in m.costs)} | "
        f"{sum(c.unusable for c in m.costs)} | | "
        f"**{sum((c.amount for c in m.costs), Decimal(0))}** |",
        "",
        f"- Références ou textes conservés faute de réponse utilisable : {m.kept_unusable}",
        f"- Durée, du premier au dernier appel : {_num(m.duration_minutes, 1)} min",
        "",
        "### Configuration",
        "",
        "| Élément | Valeur |",
        "|---|---|",
        *(f"| {k} | {v} |" for k, v in m.config.items()),
        "",
    ]
    return lines


def _chained_section(m: ModeMeasures) -> list[str]:
    e = m.end_to_end
    lines = ["### Étape 9 — diagramme de flux", ""]
    if m.flow:
        lines += [
            "| Case | Revue publiée | Outil | Écart | Écart relatif |",
            "|---|---|---|---|---|",
            *(
                f"| {_FLOW_LABELS.get(g.box, g.box)} | {g.published} | {g.tool} | "
                f"{g.difference if g.difference <= 0 else f'+{g.difference}'} | "
                f"{_pct(g.relative)} |"
                for g in m.flow
            ),
            "",
        ]
    else:
        lines += ["Aucun nombre publié du diagramme.", ""]
    if e is not None:
        lines += [
            "### De bout en bout — concordance avec la revue publiée",
            "",
            "| Mesure | Toutes les études | Études retrouvables |",
            "|---|---|---|",
            f"| Rappel par rapport à la revue publiée | {_prop(e.recall)} | "
            f"{_prop(e.recall_retrievable)} |",
            f"| Précision par rapport à la revue publiée | {_prop(e.precision)} | "
            f"{_prop(e.precision)} |",
            f"| F1 | {_num(e.f1, 3)} | {_num(e.f1_retrievable, 3)} |",
            f"| Indice de Jaccard | {_num(e.jaccard, 3)} | {_num(e.jaccard_retrievable, 3)} |",
            "",
            f"Études incluses publiées : {e.published} (retrouvables : {e.retrievable}); études "
            f"incluses par l'outil : {e.tool}; études de l'outil correspondant à une étude "
            f"publiée : {e.tool_matched}.",
            "",
        ]
    lines += [
        "### Cascade des pertes",
        "",
        "| Étape où l'étude incluse publiée est perdue | Études |",
        "|---|---|",
        *(f"| {_STAGE_LABELS[stage]} | {count} |" for stage, count in m.cascade.items()),
        "",
        "### Descripteurs automatiques des écarts",
        "",
        f"- Études perdues au tri des résumés sans résumé : {m.lost_without_abstract}",
        "- Premier critère cité par l'IA pour les exclure : "
        + (
            "; ".join(f"{code or 'aucun'} : {count}" for code, count in m.lost_by_criterion.items())
            or "—"
        ),
        f"- Inclusions de l'outil absentes de la revue publiée, par année : dans la période de "
        f"la recherche d'origine : {m.extra_years.get('within', 0)}; après : "
        f"{m.extra_years.get('after', 0)}; année inconnue : {m.extra_years.get('unknown', 0)}",
        "- Étape où les auteurs les ont écartées : non disponible (liste des exclusions au "
        "texte intégral non fournie)",
        "",
        "Ces descripteurs décrivent les écarts; ils ne tranchent pas.",
        "",
    ]
    return lines


def report_markdown(
    sheet: ReviewSheet,
    standard: Standard,
    measures: Sequence[ModeMeasures],
    *,
    generated_at: datetime,
    tool_version: str,
) -> str:
    """The report in French: numbers and configuration only."""
    out_of_search = sum(1 for s in standard.studies if not s.in_search)
    lines = [
        f"# Réplication — {sheet.id}",
        "",
        "Simulation de réplication — ne constitue pas une revue.",
        "",
        f"- Date : {generated_at:%Y-%m-%d}; revue-portee {tool_version}",
        "- Nature : concordance avec la revue publiée, référence par définition; aucun écart "
        "n'est arbitré (docs/11-plan-de-replication.md §9). La concordance est une borne "
        "prudente : les choix des auteurs comptent contre l'outil.",
        f"- Norme de référence : {len(standard.studies)} études incluses publiées, dont "
        f"{out_of_search} hors de toute base interrogée; SHA-256 de incluses.csv : "
        f"{standard.sha256[:16]}…",
        "- Intervalles : Wilson à 95 %.",
        "",
    ]
    for m in measures:
        lines += _section(m)
    return "\n".join(lines).rstrip() + "\n"
