"""The reporting checklist (PRISMA-ScR) filled from the project (EF-DEC-02, tranche 4.3).

For each item of a checklist stored as data (``domain.reporting_checklist``), the tool
proposes a text or a place in the report from the project data, through the sources the
item names; the team completes and checks it. A source the tool does not know (a new
item of a new version) leaves the item to the team and is reported as unknown: adding
PRISMA-ScR 2026 needs a new file, not new code.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from revue_portee.domain.criteria import CriterionKind
from revue_portee.domain.protocol import ProtocolSection
from revue_portee.domain.reporting_checklist import ReportingChecklist, ReportingItem
from revue_portee.i18n import translator
from revue_portee.reporting.document import Block, Document, Heading, Paragraph, Table
from revue_portee.reporting.formats import date, integer, separator
from revue_portee.reporting.methods import MethodsData
from revue_portee.reporting.protocol import ProtocolData

__all__ = [
    "RESOLVERS",
    "ChecklistFacts",
    "FilledItem",
    "build_checklist",
    "fill_checklist",
]

type Translate = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class ChecklistFacts:
    """What the project knows, gathered by the use case."""

    protocol: ProtocolData
    methods: MethodsData
    narrative_fields: int = 0  # fields whose narrative synthesis a person revised
    stakeholders: int = 0
    comments: int = 0


type Resolver = Callable[[Translate, ChecklistFacts, str], str | None]


def _title(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    title = f.protocol.project.title
    named = any(w in title.casefold() for w in ("scoping review", "revue de portée"))
    text = _("Title of the report: « {title} ».").format(title=title)
    if not named:
        text += " " + _("Add « scoping review » to the title.")
    return text


def _summary(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    full = f.methods.flow.full_text
    included = (
        full.studies if full and full.studies is not None else (full.included if full else None)
    )
    if included is None:
        return None
    return _(
        "Abstract of the report, to write; numbers to report: {identified} records "
        "identified, {included} sources of evidence included."
    ).format(identified=integer(f.methods.flow.identified, language),
             included=integer(included, language))  # fmt: skip


def _protocol_text(section: ProtocolSection) -> Resolver:
    def resolve(_: Translate, f: ChecklistFacts, language: str) -> str | None:
        if not f.protocol.text.text(section):
            return None
        return _("Introduction; drawn from the protocol (section « {section} »).").format(
            section=section.value
        )

    return resolve


def _question(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    framing = f.protocol.framing
    if framing is None:
        return None
    pcc = separator(language).join(
        f"{name}: {value}" for name, value in (
            (_("population"), framing.population), (_("concept"), framing.concept),
            (_("context"), framing.context),
        ) if value
    )  # fmt: skip
    text = _("Review question: « {question} ».").format(question=framing.question)
    return f"{text} {pcc}." if pcc else text


def _registration(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    registration = f.protocol.registration
    if registration is None:
        return None
    return _("Protocol registered on OSF on {date}: DOI {doi}.").format(
        date=registration.registered_on.isoformat(), doi=registration.doi
    )


def _criteria(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    version = f.protocol.criteria
    if version is None:
        return None
    kinds = [c.kind for c in version.criteria]
    return _(
        "Criteria version {number}: {inclusion} inclusion and {exclusion} exclusion "
        "criteria (Methods; the protocol gives each with its guidance)."
    ).format(number=version.number,
             inclusion=sum(k is CriterionKind.INCLUSION for k in kinds),
             exclusion=sum(k is CriterionKind.EXCLUSION for k in kinds))  # fmt: skip


def _deviations(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    count = len(f.protocol.deviations) + len(f.protocol.grid_deviations)
    if not count and not f.methods.changes:
        return None
    return _(
        "Changes after the protocol: {deviations} versions reported as deviations; "
        "{changes} criteria changes assessed for their impact during screening."
    ).format(deviations=count, changes=len(f.methods.changes))


def _databases(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    if not f.protocol.counts:
        imported = f.methods.flow.identified_by_source
        if not imported:
            return None
        listed = separator(language).join(
            f"{name} ({integer(n, language)})" for name, n in imported.items()
        )
        return _("Databases, by records imported: {databases}; give the date of each "
                 "search.").format(databases=listed)  # fmt: skip
    by_query = {q.id: q.translation.database.display_name for q in f.protocol.queries}
    runs = sorted(f.protocol.counts, key=lambda r: by_query.get(r.query_id, ""))
    listed = separator(language).join(
        _("{database} (searched on {date})").format(
            database=by_query.get(r.query_id, "?"), date=date(r.executed_at)
        )
        for r in runs
    )
    return _("Databases: {databases}.").format(databases=listed)


def _queries(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    if not f.protocol.queries:
        return None
    return _(
        "Full search strategies of the {count} databases, as run: appendix of the protocol "
        "(exports/protocole-{language}.md)."
    ).format(count=len(f.protocol.queries), language=language)


def _screening(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    m = f.methods
    if m.screening is None:
        return None
    text = _(
        "Titles and abstracts: {references} references screened by {people} person(s), with "
        "the AI ({model}) as a second reviewer that never excluded alone; disagreements "
        "reconciled by the person: {disagreements}."
    ).format(references=integer(m.screening.references, language), people=m.human_reviewers,
             model=m.model, disagreements=m.screening.disagreements)  # fmt: skip
    if m.pilot is not None:
        text += " " + _("Pilot of {size} references before screening (seed {seed}).").format(
            size=m.pilot.sample_size, seed=m.pilot.seed
        )
    return (
        text
        + " "
        + _("Details: methods section (exports/methode-{language}.md).").format(language=language)
    )


def _fulltext(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    ft = f.methods.full_text
    if ft is None:
        return None
    mode = _("blind double screening") if ft.mode == "blind" else _("assisted screening")
    return _("Full texts: {texts} assessed in {mode}.").format(
        texts=integer(ft.texts, language), mode=mode
    )


def _charting(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    ex = f.methods.extraction
    if ex is None:
        return None
    text = _(
        "Grid version {version} ({fields} fields); every value checked by the person "
        "(validated {validated}, corrected {corrected}, rejected {rejected}, extracted "
        "{extracted})."
    ).format(version=ex.grid_version, fields=ex.fields, validated=ex.validated,
             corrected=ex.corrected, rejected=ex.rejected, extracted=ex.extracted)  # fmt: skip
    if ex.ai_studies:
        text += " " + _(
            "Pre-filled by the AI ({model}) for {studies} sources, with quotes "
            "checked at their page."
        ).format(model=ex.model, studies=ex.ai_studies)
    if ex.pilot_studies:
        text += " " + _("Charting pilot on {studies} sources.").format(studies=ex.pilot_studies)
    return text


def _fields(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    grid = f.protocol.grid
    if grid is None or not grid.fields:
        return None
    return _("Data items: {fields} (definitions: appendix of the protocol).").format(
        fields=separator(language).join(f"{g.code} {g.label}" for g in grid.sorted_fields())
    )


def _appraisal(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    text = f.protocol.text.text(ProtocolSection.APPRAISAL)
    if text:
        return _("Critical appraisal: see the protocol (section « appraisal »).")
    return _("Not done: critical appraisal is optional in a scoping review; say so.")


def _synthesis_methods(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    if f.methods.extraction is None:
        return None
    return _(
        "Frequency tables, cross tables and evidence maps of the charted fields "
        "(exports/synthese/), and a narrative synthesis by field."
    )


def _flow(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    flow = f.methods.flow
    text = _(
        "Flow diagram (exports/diagramme-{language}.svg): {identified} records identified, "
        "{duplicates} duplicates removed, {screened} screened, {excluded} excluded."
    ).format(language=language, identified=integer(flow.identified, language),
             duplicates=integer(flow.duplicates_removed, language),
             screened=integer(flow.screened, language),
             excluded=integer(flow.excluded, language))  # fmt: skip
    if flow.full_text is not None:
        reasons = separator(language).join(
            f"{code} {n}" for code, n in sorted(flow.full_text.excluded_by_reason.items())
        )
        text += " " + _("Full texts assessed: {assessed}; excluded with reasons: {reasons}; "
                        "included: {included}.").format(
            assessed=integer(flow.full_text.assessed, language), reasons=reasons or "0",
            included=integer(flow.full_text.included, language),
        )  # fmt: skip
    return text


def _characteristics(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    if f.methods.extraction is None:
        return None
    return _("Table of the characteristics of each source: exports/donnees-extraites.csv "
             "(values decided by the person), with the references.")  # fmt: skip


def _individual(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    if f.methods.extraction is None:
        return None
    return _("Data of each source relevant to the questions: exports/donnees-extraites.csv.")


def _synthesis_results(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    if not f.narrative_fields:
        return None
    return _(
        "Narrative synthesis revised for {fields} fields, each sentence citing its sources "
        "(exports/synthese/narratif-{language}.md); tables and maps in exports/synthese/."
    ).format(fields=f.narrative_fields, language=language)


def _limitations(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    facts = []
    if f.methods.flow.not_retrieved:
        facts.append(_("{count} reports not retrieved").format(count=f.methods.flow.not_retrieved))
    if f.methods.screening is not None:
        facts.append(_("AI used as a second reviewer (see its validation in the methods)"))
    if f.methods.extraction is not None and f.methods.extraction.ai_studies:
        facts.append(_("AI pre-filling of the charting, checked by the person"))
    if not facts:
        return None
    return _("To discuss among the limitations: {facts}.").format(
        facts=separator(language).join(facts)
    )


def _funding(_: Translate, f: ChecklistFacts, language: str) -> str | None:
    if not f.protocol.text.text(ProtocolSection.FUNDING):
        return None
    return _("Funding: see the protocol (section « funding »).")


RESOLVERS: dict[str, Resolver] = {
    "title": _title,
    "summary": _summary,
    "protocol.background": _protocol_text(ProtocolSection.BACKGROUND),
    "protocol.objectives": _protocol_text(ProtocolSection.OBJECTIVES),
    "framing.question": _question,
    "registration": _registration,
    "criteria": _criteria,
    "deviations": _deviations,
    "databases": _databases,
    "queries": _queries,
    "screening": _screening,
    "fulltext": _fulltext,
    "charting": _charting,
    "grid.fields": _fields,
    "appraisal": _appraisal,
    "synthesis.methods": _synthesis_methods,
    "flow": _flow,
    "results.characteristics": _characteristics,
    "results.individual": _individual,
    "synthesis.results": _synthesis_results,
    "limitations": _limitations,
    "protocol.funding": _funding,
    # Left to the team on purpose: the tool has nothing to propose for them.
    "summary.evidence": lambda _, f, language: None,
    "conclusions": lambda _, f, language: None,
}


@dataclass(frozen=True, slots=True)
class FilledItem:
    item: ReportingItem
    proposals: tuple[str, ...]  # what the tool proposes, from the project
    unknown: tuple[str, ...]  # sources the tool does not know (a new version)

    @property
    def to_complete(self) -> bool:
        return not self.proposals


def fill_checklist(
    checklist: ReportingChecklist, facts: ChecklistFacts, *, language: str
) -> list[FilledItem]:
    _ = translator(language)
    filled = []
    for item in checklist.items:
        proposals, unknown = [], []
        for source in item.sources:
            resolver = RESOLVERS.get(source)
            if resolver is None:
                unknown.append(source)
                continue
            found = resolver(_, facts, language)
            if found:
                proposals.append(found)
        filled.append(FilledItem(item=item, proposals=tuple(proposals), unknown=tuple(unknown)))
    return filled


def build_checklist(
    checklist: ReportingChecklist,
    filled: list[FilledItem],
    *,
    project_title: str,
    language: str,
    tool_version: str,
    generated_at: datetime,
) -> Document:
    _ = translator(language)
    title = _("{title}: {checklist} {version} checklist (draft)").format(
        title=project_title, checklist=checklist.name, version=checklist.version
    )
    done = sum(1 for f in filled if not f.to_complete)
    blocks: list[Block] = [
        Heading(level=1, text=title),
        Paragraph(
            text=_(
                "Generated by revue-portee {version} on {date} from the project data: for each "
                "item, a text or a place in the report proposed by the tool, to check and "
                "complete. Items with a proposal: {done} of {total}."
            ).format(version=tool_version, date=date(generated_at), done=done, total=len(filled))
        ),
        Table(
            header=(_("No."), _("Item"), _("Proposal")),
            rows=tuple(
                (
                    f.item.id + (" " + _("(optional)") if f.item.optional else ""),
                    f.item.label(language),
                    " ".join(f.proposals) if f.proposals else _("To be completed by the team."),
                )
                for f in filled
            ),
        ),
        Paragraph(text=_("Source of the checklist: {source}").format(source=checklist.source)),
    ]
    unknown = sorted({s for f in filled for s in f.unknown})
    if unknown:
        blocks.append(
            Paragraph(
                text=_(
                    "Data sources this version of the tool does not know (items left to "
                    "the team): {sources}."
                ).format(sources=", ".join(unknown)),
                placeholder=True,
            )
        )
    return Document(title=title, language=language, generated_at=generated_at,
                    blocks=tuple(blocks))  # fmt: skip
