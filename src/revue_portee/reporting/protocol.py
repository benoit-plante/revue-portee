"""Scoping review protocol, in Markdown and DOCX, French and English (EF-CAD-06 to 08).

The protocol follows the elements of Peters et al. (2022) (``resources/protocol``):
each element has a section, filled from the project data (framing, criteria, AI
configuration, registration) and from the free text written by the team; what is
still missing is shown as a placeholder. Appendices give the criteria in full, the
status of the Peters et al. checklist and the correspondence with the OSF
*Generalized Systematic Review Registration* form.

Fixed text goes through the translation catalog (``_`` is the translator of the
export language), so that the same builder produces both languages (ENF-LAN-04).
The team's own text is reproduced as written.
"""

from collections.abc import Callable, Iterable

from pydantic import AwareDatetime, BaseModel, ConfigDict

from revue_portee.ai.settings import AISettings, TaskStatus
from revue_portee.domain.changes import ChangeType, CriterionChange
from revue_portee.domain.criteria import CriteriaVersion, Criterion, CriterionKind, PccElement
from revue_portee.domain.framing import Framing
from revue_portee.domain.project import Project, Reviewer
from revue_portee.domain.protocol import (
    Checklist,
    OsfForm,
    ProtocolRegistration,
    ProtocolSection,
    ProtocolText,
)
from revue_portee.domain.search import (
    LANGUAGES,
    BlockRole,
    Database,
    QueryVersion,
    SearchRun,
    StrategyVersion,
    format_term,
)
from revue_portee.i18n import translator
from revue_portee.reporting.document import (
    Block,
    BulletList,
    Code,
    Document,
    Heading,
    Paragraph,
    Table,
    section_blocks,
)
from revue_portee.reporting.formats import date, integer, number, separator

__all__ = [
    "ChecklistStatus",
    "Deviation",
    "ProtocolData",
    "build_protocol",
    "change_labels",
    "checklist_status",
]

type Translate = Callable[[str], str]
S = ProtocolSection


class Deviation(BaseModel):
    """A criteria version activated after the protocol was registered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int
    activated_at: AwareDatetime
    rationale: str
    changes: tuple[CriterionChange, ...] = ()


class ProtocolData(BaseModel):
    """Everything the protocol is generated from (read by ``protocol/document.py``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project: Project
    reviewers: tuple[Reviewer, ...]
    framing: Framing | None
    criteria: CriteriaVersion | None
    text: ProtocolText
    ai: AISettings
    registration: ProtocolRegistration | None
    deviations: tuple[Deviation, ...] = ()
    search: StrategyVersion | None = None
    queries: tuple[QueryVersion, ...] = ()  # of the search version, one per database
    counts: tuple[SearchRun, ...] = ()  # latest count of each query
    tool_version: str
    generated_at: AwareDatetime


class ChecklistStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    section: ProtocolSection
    present: bool  # the section exists in the document
    filled: bool  # and has content other than headings and placeholders


def checklist_status(blocks: Iterable[Block], checklist: Checklist) -> list[ChecklistStatus]:
    """Coverage of ``checklist`` by a document (used by tests and by the appendix)."""
    sections: dict[str, list[Block]] = {}
    for section, content in section_blocks(list(blocks)):
        sections.setdefault(section, []).extend(content)
    return [
        ChecklistStatus(
            item_id=item.id,
            section=item.section,
            present=item.section.value in sections,
            filled=any(
                not isinstance(b, Heading) and not (isinstance(b, Paragraph) and b.placeholder)
                for b in sections.get(item.section.value, [])
            ),
        )
        for item in checklist.items
    ]


# --- Helpers --------------------------------------------------------------------------


def _free_text(_: Translate, text: ProtocolText, section: ProtocolSection) -> list[Block]:
    content = text.text(section)
    if not content:
        return []
    return [Paragraph(text=part.strip()) for part in content.split("\n\n") if part.strip()]


def _todo(_: Translate, hint: str) -> Paragraph:
    return Paragraph(text=_("To be completed: {hint}").format(hint=hint), placeholder=True)


def _section(
    _: Translate,
    data: ProtocolData,
    section: ProtocolSection,
    level: int,
    title: str,
    hint: str,
    generated: Iterable[Block] = (),
) -> list[Block]:
    """Heading, generated content, then the team's text; a placeholder if empty."""
    blocks: list[Block] = [*generated, *_free_text(_, data.text, section)]
    if not blocks:
        blocks = [_todo(_, hint)]
    return [Heading(level=level, text=title, section=section.value), *blocks]


def _kind_label(_: Translate, kind: CriterionKind) -> str:
    return _("inclusion") if kind is CriterionKind.INCLUSION else _("exclusion")


def _element_label(_: Translate, element: PccElement) -> str:
    labels = {
        PccElement.POPULATION: _("Population"),
        PccElement.CONCEPT: _("Concept"),
        PccElement.CONTEXT: _("Context"),
        PccElement.OTHER: _("Cross-cutting"),
    }
    return labels[element]


def change_labels(_: Translate) -> dict[ChangeType, str]:
    """Names of the change types (shared with the web interface)."""
    return {
        ChangeType.BROADENING: _("broadening"),
        ChangeType.NARROWING: _("narrowing"),
        ChangeType.CLARIFICATION: _("clarification"),
        ChangeType.ADDED: _("added"),
        ChangeType.REMOVED: _("removed"),
    }


def _criteria_of(data: ProtocolData, element: PccElement) -> list[Criterion]:
    if data.criteria is None:
        return []
    return [c for c in data.criteria.sorted_criteria() if c.pcc_element is element]


def _criteria_bullets(_: Translate, criteria: list[Criterion]) -> list[Block]:
    if not criteria:
        return []
    return [
        BulletList(
            items=tuple(
                _("{code} ({kind}): {text}").format(
                    code=c.code, kind=_kind_label(_, c.kind), text=c.text
                )
                for c in criteria
            )
        )
    ]


def _element(
    _: Translate,
    data: ProtocolData,
    section: ProtocolSection,
    element: PccElement,
    title: str,
    framing_text: str,
    hint: str,
) -> list[Block]:
    generated: list[Block] = []
    if framing_text:
        generated.append(Paragraph(text=framing_text))
    generated += _criteria_bullets(_, _criteria_of(data, element))
    return _section(_, data, section, 3, title, hint, generated)


# --- Sections -------------------------------------------------------------------------


def _front(_: Translate, data: ProtocolData) -> list[Block]:
    title = _("{title}: a scoping review protocol").format(title=data.project.title)
    status = _("Protocol generated on {date} with revue-portee {version}.").format(
        date=date(data.generated_at), version=data.tool_version
    )
    if data.registration is None:
        registration = _("Registration: not yet registered.")
    else:
        registration = _("Registration: DOI {doi}, registered on {date}.").format(
            doi=data.registration.doi, date=data.registration.registered_on.isoformat()
        )
    team = [
        r.display_name + (f" ({r.role})" if r.role and r.role != "reviewer" else "")
        for r in data.reviewers
    ]
    return [
        Heading(level=1, text=title, section=S.TITLE.value),
        Paragraph(text=status),
        Paragraph(text=registration),
        Heading(level=2, text=_("Review team"), section=S.TEAM.value),
        BulletList(items=tuple(team)) if team else _todo(_, _("names of the review team")),
        *_section(
            _,
            data,
            S.ABSTRACT,
            2,
            _("Abstract"),
            _("objective, introduction, inclusion criteria and methods, in 250 words or less"),
        ),
    ]


def _introduction(_: Translate, data: ProtocolData) -> list[Block]:
    return [
        Heading(level=2, text=_("Introduction")),
        *_section(
            _,
            data,
            S.BACKGROUND,
            3,
            _("Background and rationale"),
            _("why the review is needed and what is already known"),
        ),
        *_section(
            _,
            data,
            S.EXISTING_REVIEWS,
            3,
            _("Preliminary search for existing reviews"),
            _("where existing or ongoing reviews were searched for, and what was found"),
        ),
        *_section(
            _,
            data,
            S.OBJECTIVES,
            2,
            _("Objective"),
            _("objective of the review"),
        ),
    ]


def _questions(_: Translate, data: ProtocolData) -> list[Block]:
    generated: list[Block] = []
    if data.framing is not None:
        generated.append(Paragraph(text=data.framing.question))
        if data.framing.secondary_questions:
            generated.append(Paragraph(text=_("Secondary questions:")))
            generated.append(BulletList(items=data.framing.secondary_questions))
    return _section(
        _,
        data,
        S.QUESTIONS,
        2,
        _("Review question"),
        _("main question (Framing page)"),
        generated,
    )


def _eligibility(_: Translate, data: ProtocolData) -> list[Block]:
    framing = data.framing or Framing(question="-")
    intro: list[Block] = []
    if data.criteria is not None and data.criteria.activated_at is not None:
        intro.append(
            Paragraph(
                text=_(
                    "Criteria version {number}, in force since {date}. Each criterion has a "
                    "stable code; Appendix I gives guidance, examples and counterexamples."
                ).format(number=data.criteria.number, date=date(data.criteria.activated_at))
            )
        )
    sources_generated: list[Block] = _criteria_bullets(_, _criteria_of(data, PccElement.OTHER))
    return [
        Heading(level=2, text=_("Eligibility criteria")),
        *intro,
        *_element(
            _,
            data,
            S.PARTICIPANTS,
            PccElement.POPULATION,
            _("Participants"),
            framing.population,
            _("population of interest (Framing and Criteria pages)"),
        ),
        *_element(
            _,
            data,
            S.CONCEPT,
            PccElement.CONCEPT,
            _("Concept"),
            framing.concept,
            _("concept of interest (Framing and Criteria pages)"),
        ),
        *_element(
            _,
            data,
            S.CONTEXT,
            PccElement.CONTEXT,
            _("Context"),
            framing.context,
            _("context of interest (Framing and Criteria pages)"),
        ),
        *_section(
            _,
            data,
            S.SOURCES,
            3,
            _("Types of sources of evidence"),
            _("study designs and sources considered (primary studies, reviews, grey literature)"),
            sources_generated,
        ),
    ]


def _task_label(_: Translate, task: str) -> str:
    labels = {
        "suggest_pcc": _("Suggestions for the framing (reformulations, PCC elements)"),
        "qualify_criterion_change": _(
            "Qualification of criteria changes (broadening, narrowing, clarification)"
        ),
        "suggest_terms": _("Suggestions of search terms and subject headings"),
        "screen_reference": _("Second reviewer at title and abstract screening"),
    }
    return labels.get(task, task)


def _ai_use(_: Translate, data: ProtocolData, language: str) -> list[Block]:
    ai: AISettings = data.ai
    rows = tuple(
        (
            _task_label(_, name),
            f"{config.provider} — {config.model}"
            if config.provider and config.model
            else _("to be determined"),
            _("configured") if config.status is TaskStatus.ENABLED else _("planned"),
        )
        for name, config in ai.tasks.items()
    )
    supervision = ai.supervision
    generated: list[Block] = [
        Paragraph(
            text=_(
                "Artificial intelligence (AI) is used under human supervision, following the "
                "RAISE recommendations. The review team remains responsible for every "
                "decision."
            )
        ),
        Table(header=(_("Task"), _("Provider and model"), _("Status")), rows=rows),
        BulletList(
            items=(
                _(
                    "Supervision: a human reviewer screens every reference; the AI acts as a "
                    "second, independent reviewer and never excludes a reference on its own."
                ),
                _(
                    "Calibration: before screening, a pilot on a random sample of {size} "
                    "references, drawn with a recorded seed and screened blind by the human "
                    "reviewer, measures agreement and calibrates the confidence of the AI "
                    "({method})."
                ).format(size=supervision.pilot_sample_size, method=supervision.calibration_method),
                _(
                    "Decision thresholds favour sensitivity, with a target of at least {target}."
                ).format(target=number(supervision.target_sensitivity, language)),
                _(
                    "Every AI suggestion is accepted, modified or rejected explicitly by a human "
                    "reviewer, and every change of the criteria is qualified by a human."
                ),
                _(
                    "Traceability: each AI output is recorded with the provider, the exact model "
                    "version returned by the API, the prompt template version, a hash of the "
                    "prompt, the parameters, the tokens used and the cost; raw responses are "
                    "kept with the project. The exact model versions will be reported with the "
                    "results."
                ),
            )
        ),
    ]
    return [
        Heading(level=3, text=_("Use of artificial intelligence"), section=S.AI_USE.value),
        *generated,
    ]


def _selection_generated(_: Translate, data: ProtocolData) -> list[Block]:
    return [
        Paragraph(
            text=_(
                "Titles and abstracts, then full texts, will be screened against the "
                "eligibility criteria by a human reviewer, with an AI model as a second, "
                "independent reviewer (see “Use of artificial intelligence”). Before "
                "screening, a pilot test on a random sample of {size} references will be "
                "used to check the shared understanding of the criteria, which may then be "
                "clarified in a new version. Disagreements between the human reviewer and "
                "the AI are reconciled by the human reviewer. The selection will be managed "
                "with revue-portee {version} and reported in a PRISMA-ScR flow diagram."
            ).format(size=data.ai.supervision.pilot_sample_size, version=data.tool_version)
        )
    ]


def _search_generated(_: Translate, data: ProtocolData, language: str) -> list[Block]:
    version = data.search
    if version is None or not version.strategy.included:
        return []
    strategy = version.strategy
    included = [b.label or b.code for b in strategy.included]
    excluded = [b.label or b.code for b in strategy.excluded]
    blocks: list[Block] = [
        Paragraph(
            text=_(
                "The search strategy combines the following concept blocks with AND: {blocks}. "
                "The terms of a block (free-text words and phrases searched in titles and "
                "abstracts, with truncation, and subject headings) are combined with OR."
            ).format(blocks=", ".join(included))
        )
    ]
    if excluded:
        blocks.append(
            Paragraph(
                text=_(
                    "Records matching the following blocks are removed with NOT: {blocks}."
                ).format(blocks=", ".join(excluded))
            )
        )
    limits = strategy.limits
    if not limits.empty:
        parts = []
        if limits.year_from or limits.year_to:
            parts.append(
                _("publication years {start} to {end}").format(
                    start=limits.year_from or "…", end=limits.year_to or "…"
                )
            )
        if limits.languages:
            parts.append(
                _("languages: {languages}").format(
                    languages=", ".join(_language_name(_, code) for code in limits.languages)
                )
            )
        separator = " ; " if language == "fr" else "; "
        blocks.append(Paragraph(text=_("Limits: {limits}.").format(limits=separator.join(parts))))
    databases = [q.database.display_name for q in _ordered(data.queries) if q.translation.text]
    blocks.append(
        Paragraph(
            text=_(
                "The query of each database ({databases}) is generated from version {number} of "
                "the strategy ({date}) and given in Appendix II; each version of the strategy "
                "and of the queries is kept with its date and its number of results."
            ).format(
                databases=", ".join(databases),
                number=version.number,
                date=date(version.created_at),
            )
        )
    )
    return blocks


def _sources_generated(_: Translate, data: ProtocolData, language: str) -> list[Block]:
    if not data.counts:
        return []
    by_query = {q.id: q.database for q in data.queries}
    items = tuple(
        _("{database} ({date}): {count}").format(
            database=by_query[run.query_id].display_name,
            count=integer(run.result_count or 0, language),
            date=date(run.executed_at),
        )
        for run in data.counts
        if run.query_id in by_query
    )
    if not items:
        return []
    return [
        Paragraph(text=_("Preliminary number of records retrieved by the queries of Appendix II:")),
        BulletList(items=items),
    ]


def _ordered(queries: Iterable[QueryVersion]) -> list[QueryVersion]:
    order = {database: position for position, database in enumerate(Database)}
    return sorted(queries, key=lambda q: order[q.database])


def _language_name(_: Translate, code: str) -> str:
    names = {
        "en": _("English"),
        "fr": _("French"),
        "es": _("Spanish"),
        "de": _("German"),
        "pt": _("Portuguese"),
        "it": _("Italian"),
    }
    return names.get(code, LANGUAGES.get(code, code))


def _search_appendix(_: Translate, data: ProtocolData, language: str) -> list[Block]:
    version = data.search
    if version is None or not data.queries:
        return [_todo(_, _("complete search strategy for at least one database"))]
    rows = tuple(
        (
            b.code,
            b.label,
            _("exclusion (NOT)") if b.role is BlockRole.EXCLUDE else _("inclusion (AND)"),
            separator(language).join(format_term(t) for t in b.terms),
        )
        for b in version.strategy.blocks
    )
    blocks: list[Block] = [
        Paragraph(
            text=_("Concept blocks of version {number} of the search strategy ({date}).").format(
                number=version.number, date=date(version.created_at)
            )
        ),
        Table(header=(_("Block"), _("Label"), _("Role"), _("Terms")), rows=rows),
    ]
    for query in _ordered(data.queries):
        if not query.translation.text:
            continue
        blocks.append(Paragraph(text=query.database.display_name))
        blocks.append(Code(text=query.translation.text))
        if query.database is Database.OPENALEX:
            blocks.append(
                Paragraph(text=_("Value of the « filter » parameter of the OpenAlex API (works)."))
            )
    return blocks


def _methods(_: Translate, data: ProtocolData, language: str) -> list[Block]:
    framework: list[Block] = [
        Paragraph(
            text=_(
                "This scoping review will be conducted in accordance with the JBI methodology "
                "for scoping reviews and reported following the PRISMA extension for scoping "
                "reviews (PRISMA-ScR). This protocol follows the guidance of Peters et al. "
                "(2022)."
            )
        ),
        Paragraph(
            text=_("The protocol is registered on OSF: DOI {doi}.").format(
                doi=data.registration.doi
            )
            if data.registration is not None
            else _("The protocol will be registered on OSF before the search is run.")
        ),
    ]
    return [
        Heading(level=2, text=_("Methods")),
        Heading(level=3, text=_("Methodological framework"), section=S.METHODS_FRAMEWORK.value),
        *framework,
        *_section(
            _,
            data,
            S.SEARCH,
            3,
            _("Search strategy"),
            _(
                "steps of the search, draft search for one database (Appendix II), language "
                "and date limits with their justification"
            ),
            _search_generated(_, data, language),
        ),
        *_section(
            _,
            data,
            S.INFORMATION_SOURCES,
            3,
            _("Information sources"),
            _("databases, interfaces and grey literature sources"),
            _sources_generated(_, data, language),
        ),
        *_section(
            _,
            data,
            S.SELECTION,
            3,
            _("Source of evidence selection"),
            "",
            _selection_generated(_, data),
        ),
        *_ai_use(_, data, language),
        *_section(
            _,
            data,
            S.EXTRACTION,
            3,
            _("Data extraction"),
            _("data to chart, draft charting tool (Appendix III), pilot and revisions"),
        ),
        *_section(
            _,
            data,
            S.ANALYSIS,
            3,
            _("Data analysis and presentation"),
            _("how results will be summarized and presented (tables, figures, narrative)"),
        ),
        *_section(
            _,
            data,
            S.APPRAISAL,
            3,
            _("Critical appraisal"),
            _("whether a critical appraisal of the sources is planned, and why"),
        ),
        *_section(
            _,
            data,
            S.CONSULTATION,
            3,
            _("Consultation"),
            _("whether knowledge users will be consulted, and how (optional)"),
        ),
    ]


def _deviations(_: Translate, data: ProtocolData) -> list[Block]:
    blocks: list[Block] = [
        Paragraph(
            text=_(
                "Every change to the eligibility criteria creates a new, dated version with a "
                "rationale, and each change is qualified (broadening, narrowing, "
                "clarification, addition, removal). After registration, every new version is "
                "reported here as a deviation from the protocol."
            )
        )
    ]
    for deviation in data.deviations:
        changes = ", ".join(
            f"{c.code} ({change_labels(_)[c.change_type]})" for c in deviation.changes
        )
        blocks.append(
            Paragraph(
                text=_("Criteria version {number} ({date}): {rationale}").format(
                    number=deviation.number,
                    date=date(deviation.activated_at),
                    rationale=deviation.rationale,
                )
                + (f" — {changes}" if changes else "")
            )
        )
    return [
        Heading(level=2, text=_("Deviations from the protocol"), section=S.DEVIATIONS.value),
        *blocks,
    ]


_FIXED_REFERENCES = (
    "Peters MDJ, Godfrey C, McInerney P, Khalil H, Larsen P, Marnie C, Pollock D, Tricco AC, "
    "Munn Z. Best practice guidance and reporting items for the development of scoping review "
    "protocols. JBI Evid Synth. 2022;20(4):953-968. doi:10.11124/JBIES-21-00242",
    "Tricco AC, Lillie E, Zarin W, et al. PRISMA Extension for Scoping Reviews (PRISMA-ScR): "
    "Checklist and Explanation. Ann Intern Med. 2018;169(7):467-473. doi:10.7326/M18-0850",
    "Pollock D, Peters MDJ, Tricco AC, Munn Z, et al. Scoping reviews (2026). In: Aromataris E, "
    "et al., editors. JBI Manual for Evidence Synthesis. JBI; 2024. doi:10.46658/JBIMES-24-09",
    "Thomas J, Flemyng E, Noel-Storr A, et al. Responsible AI in Evidence Synthesis (RAISE): "
    "guidance and recommendations. OSF; 2025. doi:10.17605/OSF.IO/FWAUD",
)


def _closing(_: Translate, data: ProtocolData) -> list[Block]:
    return [
        *_section(
            _,
            data,
            S.ACKNOWLEDGEMENTS,
            2,
            _("Acknowledgements"),
            _("people and organizations to thank"),
        ),
        *_section(
            _, data, S.FUNDING, 2, _("Funding"), _("funding sources, or the absence of funding")
        ),
        *_section(
            _,
            data,
            S.CONFLICTS,
            2,
            _("Conflicts of interest"),
            _("conflicts of interest, or their absence"),
        ),
        Heading(level=2, text=_("References"), section=S.REFERENCES.value),
        BulletList(items=_FIXED_REFERENCES),
        *_free_text(_, data.text, S.REFERENCES),
    ]


def _criteria_table(_: Translate, data: ProtocolData) -> list[Block]:
    if data.criteria is None or not data.criteria.criteria:
        return [_todo(_, _("eligibility criteria (Criteria page)"))]
    return [
        Table(
            header=(
                _("Code"),
                _("PCC element"),
                _("Kind"),
                _("Criterion"),
                _("Guidance"),
                _("Examples"),
                _("Counterexamples"),
            ),
            rows=tuple(
                (
                    c.code,
                    _element_label(_, c.pcc_element),
                    _kind_label(_, c.kind),
                    c.text,
                    c.guidance,
                    "; ".join(c.examples),
                    "; ".join(c.counterexamples),
                )
                for c in data.criteria.sorted_criteria()
            ),
        )
    ]


def _appendices(_: Translate, data: ProtocolData, language: str) -> list[Block]:
    return [
        Heading(level=2, text=_("Appendices"), section=S.APPENDICES.value),
        Heading(level=3, text=_("Appendix I: Eligibility criteria in full")),
        *_criteria_table(_, data),
        Heading(level=3, text=_("Appendix II: Search strategy")),
        *_search_appendix(_, data, language),
        Heading(level=3, text=_("Appendix III: Data extraction instrument")),
        _todo(_, _("draft charting tool")),
    ]


def _checklist_appendix(
    _: Translate, language: str, blocks: list[Block], checklist: Checklist, titles: dict[str, str]
) -> list[Block]:
    statuses = {s.item_id: s for s in checklist_status(blocks, checklist)}
    rows = []
    for item in checklist.items:
        status = statuses[item.id]
        state = _("written") if status.filled else _("to be completed")
        if item.optional and not status.filled:
            state = _("to be completed if applicable")
        rows.append((item.id, item.label(language), titles.get(item.section.value, ""), state))
    note = (
        []
        if checklist.verified
        else [
            Paragraph(
                text=_(
                    "The list of elements is to be checked against the checklist of the article."
                ),
                placeholder=True,
            )
        ]
    )
    return [
        Heading(level=3, text=_("Appendix IV: Protocol elements (Peters et al., 2022)")),
        *note,
        Table(header=(_("Element"), _("Description"), _("Section"), _("Status")), rows=tuple(rows)),
    ]


def _osf_appendix(_: Translate, language: str, osf: OsfForm, titles: dict[str, str]) -> list[Block]:
    rows = tuple(
        (
            item.id,
            item.label(language),
            "; ".join(titles[s.value] for s in item.sections if s.value in titles)
            or _("to be filled in directly in the OSF form, or not applicable"),
        )
        for item in osf.items
    )
    return [
        Heading(
            level=3,
            text=_(
                "Appendix V: Correspondence with the OSF Generalized Systematic Review "
                "Registration form"
            ),
        ),
        Paragraph(
            text=_("Form version {version}. Source: {source}").format(
                version=osf.version, source=osf.source
            )
        ),
        Table(header=(_("OSF item"), _("OSF field"), _("Protocol section")), rows=rows),
    ]


def build_protocol(
    data: ProtocolData, *, language: str, checklist: Checklist, osf: OsfForm
) -> Document:
    """The protocol document in ``language`` (``fr`` or ``en``)."""
    _ = translator(language)
    blocks: list[Block] = [
        *_front(_, data),
        *_introduction(_, data),
        *_questions(_, data),
        *_eligibility(_, data),
        *_methods(_, data, language),
        *_deviations(_, data),
        *_closing(_, data),
        *_appendices(_, data, language),
    ]
    titles = {b.section: b.text for b in blocks if isinstance(b, Heading) and b.section is not None}
    blocks += _checklist_appendix(_, language, blocks, checklist, titles)
    blocks += _osf_appendix(_, language, osf, titles)
    return Document(
        title=_("{title}: a scoping review protocol").format(title=data.project.title),
        language=language,
        generated_at=data.generated_at,
        blocks=tuple(blocks),
    )
