"""Draft methods section on the use of AI in title and abstract screening (EF-DEC-03).

The section follows the four parts of the CEE reporting guidance (Macura et al., 2025),
which RAISE endorses: description and rationale, validation, limitations and ethics,
funding and conflicts of interest; the results of the screening with the AI come
between validation and limitations. Every fact comes from the project (``MethodsData``,
gathered by ``screening/methods.py``); what only the team can say (why the AI was
used, limitations specific to the review, funding, conflicts of interest) is left as a
placeholder. Fixed text goes through the translation catalog, so the same builder
produces French and English (ENF-LAN-04).
"""

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from revue_portee.domain.changes import ChangeType
from revue_portee.i18n import translator
from revue_portee.reporting.document import (
    Block,
    BulletList,
    Document,
    Heading,
    Paragraph,
    Table,
)
from revue_portee.reporting.flow import FlowNumbers, ReassessmentCounts, pending_items
from revue_portee.reporting.formats import date, fixed, integer, number, percent, separator
from revue_portee.reporting.protocol import change_labels

__all__ = [
    "ChangeSummary",
    "CostLine",
    "MethodsData",
    "ModelUse",
    "PilotSummary",
    "ScreeningSummary",
    "ThresholdSummary",
    "ToolValidation",
    "ValidationDataset",
    "build_methods",
]

type Translate = Callable[[str], str]


class ValidationDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    references: int
    included: int
    sensitivity: Decimal
    sensitivity_low: Decimal
    sensitivity_high: Decimal
    specificity: Decimal
    cost_per_1000: Decimal


class ValidationConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task: str
    prompt_template_version: str
    model: str
    exclude_below: Decimal
    include_above: Decimal


class ToolValidation(BaseModel):
    """The developer's validation of the AI screening (``resources/reporting``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    date: dt.date
    source: str
    configuration: ValidationConfiguration
    reference_standard: str
    datasets: tuple[ValidationDataset, ...]


class ModelUse(BaseModel):
    """Calls answered by one exact model version (ENF-TRA-01)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model_requested: str
    model_returned: str
    calls: int
    first: AwareDatetime
    last: AwareDatetime


class PilotSummary(BaseModel):
    """The pilot round the thresholds were set after (or the latest one)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int
    sample_size: int
    seed: int
    criteria_version: int
    compared: int  # references decided by both the person and the AI
    agreement: float | None
    kappa: float | None
    ac1: float | None
    sensitivity: float | None
    sensitivity_interval: tuple[float, float] | None
    specificity: float | None
    specificity_interval: tuple[float, float] | None
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    calibration_method: str | None = None
    calibration_fitted_on: int = 0
    rounds: int = 1  # pilot rounds of the project


class ThresholdSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exclude_below: float
    include_above: float
    calibrated: bool
    set_by_person: bool
    target_sensitivity: Decimal | None = None
    justification: str = ""


class ScreeningSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    references: int  # in the main screening
    by_person: int  # references with an independent human decision
    by_ai: int  # references with an AI decision
    by_both: int
    disagreements: int
    reconciled: int
    reconciled_with_ai: int  # the final decision keeps or excludes as the AI did


class ChangeSummary(BaseModel):
    """A criteria version activated during the screening, and its reassessment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    changes: tuple[tuple[str, ChangeType], ...]  # code, type
    justification: str
    sampled: bool  # clarifications reassessed on a sample (D-077)
    counts: ReassessmentCounts


class CostLine(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: str  # pilot, main, reassessment, unlinked
    calls: int
    amount: Decimal


class MethodsData(BaseModel):
    """Everything the methods section is generated from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_title: str
    tool_version: str
    generated_at: AwareDatetime
    human_reviewers: int
    provider: str  # configured for screen_reference
    model: str
    params: dict[str, str]
    templates: tuple[tuple[str, str, int], ...]  # template, version, calls
    models: tuple[ModelUse, ...]
    pilot: PilotSummary | None
    thresholds: ThresholdSummary
    screening: ScreeningSummary | None
    flow: FlowNumbers
    changes: tuple[ChangeSummary, ...]
    costs: tuple[CostLine, ...]
    other_costs: CostLine  # every other AI task of the project
    currency: str
    prices_as_of: str
    validation: ToolValidation


# --- Helpers --------------------------------------------------------------------------


def _todo(_: Translate, hint: str) -> Paragraph:
    return Paragraph(text=_("To be completed: {hint}").format(hint=hint), placeholder=True)


def _quoted(text: str, language: str) -> str:
    return f"« {text} »" if language == "fr" else f"“{text}”"


def _optional(value: float | None, language: str, places: int = 2) -> str:
    return "—" if value is None else fixed(value, places, language)


def _share(
    _: Translate, value: float | None, interval: tuple[float, float] | None, language: str
) -> str:
    if value is None:
        return "—"
    if interval is None:
        return percent(value, language)
    low, high = (percent(v, language) for v in interval)
    return _("{value} ({low} to {high})").format(value=percent(value, language), low=low, high=high)


def _money(amount: Decimal, language: str) -> str:
    """Amount with four decimals: the phases of a small project cost fractions of a cent."""
    return number(amount.quantize(Decimal("0.0001")), language)


def _ratio(part: int, whole: int, language: str) -> str:
    return "—" if whole == 0 else percent(part / whole, language)


# --- Sections --------------------------------------------------------------------------


def _description(_: Translate, data: MethodsData, language: str) -> list[Block]:
    blocks: list[Block] = [Heading(level=2, text=_("Description and rationale"))]
    if not data.models:
        blocks.append(Paragraph(text=_("No AI was used to screen titles and abstracts.")))
        return blocks
    params = separator(language).join(f"{k}={v}" for k, v in sorted(data.params.items()))
    templates = separator(language).join(
        _("{template}, version {version} ({calls} calls)").format(
            template=t, version=v, calls=integer(n, language)
        )
        for t, v, n in data.templates
    )
    blocks += [
        Paragraph(
            text=_(
                "Titles and abstracts were screened with revue-portee {version}, free software "
                "(AGPL-3.0-or-later), with a large language model as a traceable second "
                "reviewer of every reference."
            ).format(version=data.tool_version)
        ),
        Paragraph(
            text=_(
                "Model configured: {provider} {model}, with the parameters {params}. Prompt "
                "template: {templates}. Exact versions returned by the provider's API:"
            ).format(
                provider=data.provider, model=data.model, params=params or "—",
                templates=templates,
            )
        ),
        Table(
            header=(
                _("Provider"),
                _("Model requested"),
                _("Exact version returned"),
                _("Calls"),
                _("First call"),
                _("Last call"),
            ),
            rows=tuple(
                (
                    m.provider,
                    m.model_requested,
                    m.model_returned,
                    integer(m.calls, language),
                    date(m.first),
                    date(m.last),
                )
                for m in data.models
            ),
        ),
    ]  # fmt: skip
    supervision = _(
        "Supervision: the person (human reviewers: {reviewers}) screened every reference without "
        "seeing "
        "the AI's decision; the AI screened every reference independently. When one kept a "
        "reference (include or uncertain) and the other excluded it, the person took the "
        "final decision with the AI's rationale in view."
    ).format(reviewers=data.human_reviewers)
    if data.flow.excluded_by_automation == 0:
        supervision += " " + _("No reference was excluded by the AI alone.")
    blocks.append(Paragraph(text=supervision))
    blocks.append(_todo(_, _("why AI was used for this task and why this model was chosen")))
    return blocks


def _differences(_: Translate, data: MethodsData) -> list[str]:
    evaluated = data.validation.configuration
    differences = []
    if data.model != evaluated.model:
        differences.append(_("model {model}").format(model=data.model))
    versions = {version for _t, version, _n in data.templates}
    if versions and versions != {evaluated.prompt_template_version}:
        differences.append(
            _("prompt template version {versions}").format(versions=", ".join(sorted(versions)))
        )
    return differences


def _tool_validation(_: Translate, data: MethodsData, language: str) -> list[Block]:
    validation = data.validation
    evaluated = validation.configuration
    blocks: list[Block] = [
        Paragraph(
            text=_(
                "The tool's developer evaluated the default configuration ({model}, prompt "
                "template version {version}, thresholds {low} and {high}) on {count} "
                "systematic reviews of the SYNERGY dataset, against their full-text inclusions "
                "({date}; {source}):"
            ).format(
                model=evaluated.model,
                version=evaluated.prompt_template_version,
                low=number(evaluated.exclude_below, language),
                high=number(evaluated.include_above, language),
                count=len(validation.datasets),
                date=validation.date.isoformat(),
                source=validation.source,
            )
        ),
        Table(
            header=(
                _("Dataset"),
                _("References"),
                _("Included"),
                _("Sensitivity (95% CI)"),
                _("Specificity"),
                _("Cost per 1,000 references (USD)"),
            ),
            rows=tuple(
                (
                    d.name,
                    integer(d.references, language),
                    integer(d.included, language),
                    _share(
                        _,
                        float(d.sensitivity),
                        (float(d.sensitivity_low), float(d.sensitivity_high)),
                        language,
                    ),
                    percent(float(d.specificity), language),
                    number(d.cost_per_1000, language),
                )
                for d in validation.datasets
            ),
        ),
    ]
    differences = _differences(_, data)
    if data.models and differences:
        blocks.append(
            Paragraph(
                text=_(
                    "The configuration of this review differs from the one evaluated ({items}): "
                    "these results do not apply directly."
                ).format(items=separator(language).join(differences))
            )
        )
    return blocks


def _pilot(_: Translate, pilot: PilotSummary | None, language: str) -> list[Block]:
    if pilot is None:
        return [Paragraph(text=_("No pilot round was recorded before the screening."))]
    blocks: list[Block] = [
        Paragraph(
            text=_(
                "Pilot: {size} references drawn at random (seed {seed}) were screened by the "
                "person, blind to the AI, and by the AI, with criteria version {version} "
                "(round {number} of {rounds}). Both decided {compared} of them; the AI's "
                "decision is compared with the person's, keep (include or uncertain) against "
                "exclude:"
            ).format(
                size=integer(pilot.sample_size, language),
                seed=pilot.seed,
                version=pilot.criteria_version,
                number=pilot.number,
                rounds=pilot.rounds,
                compared=integer(pilot.compared, language),
            )
        ),
        Table(
            header=(_("Measure"), _("Value")),
            rows=(
                (_("Agreement"), _share(_, pilot.agreement, None, language)),
                (_("Cohen's kappa"), _optional(pilot.kappa, language)),
                (_("Gwet's AC1"), _optional(pilot.ac1, language)),
                (
                    _("Sensitivity (95% CI)"),
                    _share(_, pilot.sensitivity, pilot.sensitivity_interval, language),
                ),
                (
                    _("Specificity (95% CI)"),
                    _share(_, pilot.specificity, pilot.specificity_interval, language),
                ),
                (
                    _("Confusion matrix"),
                    _(
                        "both keep: {tp}; AI keeps, person excludes: {fp}; AI excludes, person "
                        "keeps: {fn}; both exclude: {tn}"
                    ).format(
                        tp=pilot.true_positives,
                        fp=pilot.false_positives,
                        fn=pilot.false_negatives,
                        tn=pilot.true_negatives,
                    ),
                ),
            ),
        ),
    ]
    if pilot.calibration_method is not None:
        blocks.append(
            Paragraph(
                text=_(
                    "The AI's probability of inclusion was calibrated on the pilot ({method}, "
                    "{count} decisions)."
                ).format(method=pilot.calibration_method, count=pilot.calibration_fitted_on)
            )
        )
    return blocks


def _thresholds(_: Translate, thresholds: ThresholdSummary, language: str) -> list[Block]:
    low = fixed(thresholds.exclude_below, 2, language)
    high = fixed(thresholds.include_above, 2, language)
    if thresholds.set_by_person:
        text = _(
            "Thresholds: the AI excluded a reference when its {probability} was below {low}, "
            "included it from {high}, and was uncertain in between."
        ).format(
            probability=_("calibrated probability of inclusion")
            if thresholds.calibrated
            else _("probability of inclusion"),
            low=low,
            high=high,
        )
        if thresholds.target_sensitivity is not None:
            text += " " + _("Target sensitivity: {target}.").format(
                target=percent(float(thresholds.target_sensitivity), language)
            )
        if thresholds.justification:
            text += " " + _("Justification recorded: {text}").format(
                text=_quoted(thresholds.justification, language)
            )
    else:
        text = _(
            "Thresholds: the project defaults ({low} and {high}), applied to the probability "
            "of inclusion; they were not set after a pilot."
        ).format(low=low, high=high)
    rule = _(
        "The AI never excluded a reference when an inclusion criterion could not be assessed "
        "and no criterion was failed (rule EF-SEL-07)."
    )
    return [Paragraph(text=text), Paragraph(text=rule)]


def _validation(_: Translate, data: MethodsData, language: str) -> list[Block]:
    blocks: list[Block] = [Heading(level=2, text=_("Validation"))]
    blocks += _tool_validation(_, data, language)
    if data.models:
        blocks += _pilot(_, data.pilot, language)
        blocks += _thresholds(_, data.thresholds, language)
    return blocks


def _change(_: Translate, change: ChangeSummary, language: str) -> str:
    labels = change_labels(_)
    counts = change.counts
    changes = separator(language).join(
        _("{code}: {change}").format(code=code, change=labels[kind])
        for code, kind in change.changes
    )
    text = _(
        "Criteria version {before} to {after} ({changes}). References reassessed: "
        "{reassessed}; decisions changed from keep to exclude: {kept_to_excluded}; from "
        "exclude to keep: {excluded_to_kept}."
    ).format(
        before=counts.from_version,
        after=counts.to_version,
        changes=changes or "—",
        reassessed=integer(counts.reassessed, language),
        kept_to_excluded=integer(counts.kept_to_excluded, language),
        excluded_to_kept=integer(counts.excluded_to_kept, language),
    )
    if change.sampled and any(kind is ChangeType.CLARIFICATION for _code, kind in change.changes):
        text += " " + _("Clarifications were reassessed on a random sample.")
    if not counts.completed:
        text += " " + _("The reassessment is not completed.")
    if change.justification:
        text += " " + _("Justification: {text}").format(
            text=_quoted(change.justification, language)
        )
    return text


def _costs(_: Translate, data: MethodsData, language: str) -> list[Block]:
    labels = {
        "pilot": _("Pilot"),
        "main": _("Main screening"),
        "reassessment": _("Reassessments"),
        "unlinked": _("Failed calls not linked to a round"),
    }
    lines = [c for c in data.costs if c.calls or c.phase != "unlinked"]
    total = sum((c.amount for c in lines), Decimal(0))
    rows = [
        (labels[c.phase], integer(c.calls, language), _money(c.amount, language)) for c in lines
    ]
    rows.append(
        (
            _("Total of the screening"),
            integer(sum(c.calls for c in lines), language),
            _money(total, language),
        )
    )
    blocks: list[Block] = [
        Paragraph(
            text=_(
                "Cost of the AI screening, estimated from the provider's prices of {date} "
                "({currency}):"
            ).format(date=data.prices_as_of, currency=data.currency)
        ),
        Table(header=(_("Phase"), _("Calls"), _("Cost")), rows=tuple(rows)),
    ]
    if data.other_costs.calls:
        blocks.append(
            Paragraph(
                text=_(
                    "Other uses of the AI in the project (framing, criteria, search): {calls} "
                    "calls, {amount} {currency}."
                ).format(
                    calls=integer(data.other_costs.calls, language),
                    amount=_money(data.other_costs.amount, language),
                    currency=data.currency,
                )
            )
        )
    return blocks


def _results(_: Translate, data: MethodsData, language: str) -> list[Block]:
    blocks: list[Block] = [Heading(level=2, text=_("Results of the screening with the AI"))]
    screening = data.screening
    if screening is None:
        blocks.append(Paragraph(text=_("The main screening has not started.")))
        return blocks
    flow = data.flow
    blocks.append(
        Paragraph(
            text=_(
                "References screened: {screened}; excluded: {excluded}; kept for the full text "
                "(include or uncertain): {sought}. The AI screened {ai} of the {total} "
                "references ({share}); the person screened {human}."
            ).format(
                screened=integer(flow.screened, language),
                excluded=integer(flow.excluded, language),
                sought=integer(flow.sought, language),
                ai=integer(screening.by_ai, language),
                total=integer(screening.references, language),
                share=_ratio(screening.by_ai, screening.references, language),
                human=integer(screening.by_person, language),
            )
        )
    )
    blocks.append(
        Paragraph(
            text=_(
                "Disagreements between the person and the AI (one keeps, the other excludes): "
                "{count} ({share} of the references screened by both). Reconciled: "
                "{reconciled}; the final decision followed the AI for {with_ai} and the "
                "person's first decision for {with_person}."
            ).format(
                count=integer(screening.disagreements, language),
                share=_ratio(screening.disagreements, screening.by_both, language),
                reconciled=integer(screening.reconciled, language),
                with_ai=integer(screening.reconciled_with_ai, language),
                with_person=integer(screening.reconciled - screening.reconciled_with_ai, language),
            )
        )
    )
    if data.changes:
        blocks.append(
            Paragraph(
                text=_(
                    "Criteria changed during the screening; the references each change touched "
                    "were screened again by the AI, and the person verified the decisions the "
                    "AI would change (keep or exclude):"
                )
            )
        )
        blocks.append(BulletList(items=tuple(_change(_, c, language) for c in data.changes)))
    else:
        blocks.append(Paragraph(text=_("The criteria did not change during the screening.")))
    blocks += _costs(_, data, language)
    return blocks


def _limitations(_: Translate, data: MethodsData, language: str) -> list[Block]:
    smallest = min(data.validation.datasets, key=lambda d: d.included)
    items = [
        _("The AI screened titles and abstracts only; it did not assess full texts."),
        _(
            "The tool was validated on systematic reviews in psychology, not on scoping "
            "reviews; on the smallest dataset, the sensitivity rests on {included} included "
            "references (95% CI {low} to {high})."
        ).format(
            included=smallest.included,
            low=percent(float(smallest.sensitivity_low), language),
            high=percent(float(smallest.sensitivity_high), language),
        ),
        _(
            "The behaviour of a language model may change from one version to the next; the "
            "exact versions used are reported above."
        ),
        _("Only published literature was sent to the model; no participant data."),
    ]
    return [
        Heading(level=2, text=_("Limitations and ethics")),
        BulletList(items=tuple(items)),
        _todo(_, _("limitations specific to this review")),
    ]


def _funding(_: Translate) -> list[Block]:
    return [
        Heading(level=2, text=_("Funding and conflicts of interest")),
        _todo(_, _("funding of the review and of the AI use, and conflicts of interest")),
    ]


_REFERENCES = (
    "Flemyng E, Noel-Storr A, Macura B, et al. Position statement on artificial intelligence "
    "(AI) use in evidence synthesis across Cochrane, the Campbell Collaboration, JBI and the "
    "Collaboration for Environmental Evidence 2025. JBI Evid Synth. 2025;23(11):2162-2166. "
    "doi:10.11124/JBIES-25-00480",
    "Macura B, et al. Artificial intelligence reporting guidance. Collaboration for "
    "Environmental Evidence; 2025. https://environmentalevidence.org/"
    "artificial-intelligence-reporting-guidance/",
    "Thomas J, Flemyng E, Noel-Storr A, et al. Responsible AI in Evidence Synthesis (RAISE): "
    "guidance and recommendations. OSF; 2025. doi:10.17605/OSF.IO/FWAUD",
)


def build_methods(data: MethodsData, *, language: str) -> Document:
    """The draft methods section in ``language`` (fr or en)."""
    _ = translator(language)
    title = _("{title}: use of AI in title and abstract screening (methods, draft)").format(
        title=data.project_title
    )
    blocks: list[Block] = [
        Heading(level=1, text=title),
        Paragraph(
            text=_(
                "Draft generated by revue-portee {version} on {date} from the project data. "
                "Check and complete it before publication."
            ).format(version=data.tool_version, date=date(data.generated_at))
        ),
    ]
    if data.flow.provisional:
        blocks.append(
            Paragraph(
                text=_("Provisional: the screening is not finished ({items}).").format(
                    items=separator(language).join(pending_items(_, data.flow.pending, language))
                )
            )
        )
    blocks += _description(_, data, language)
    blocks += _validation(_, data, language)
    blocks += _results(_, data, language)
    blocks += _limitations(_, data, language)
    blocks += _funding(_)
    blocks += [Heading(level=2, text=_("References")), BulletList(items=_REFERENCES)]
    return Document(
        title=title,
        language=language,
        generated_at=data.generated_at,
        blocks=tuple(blocks),
    )
