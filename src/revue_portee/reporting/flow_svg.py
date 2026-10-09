"""The flow diagram as an SVG image, in French or English (EF-DEC-01, ENF-LAN-04).

The layout is computed here (boxes, arrows, phase bands, notes), then written by the
Jinja2 template ``templates/flow.svg.j2``: the output is deterministic, so the same
data always give the same file. The wording of the boxes comes from the template data
(``FlowTemplate``); the tool's own text goes through the translation catalog.
"""

import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache

from jinja2 import Environment, PackageLoader

from revue_portee.i18n import translator
from revue_portee.reporting.flow import FlowNumbers, FlowTemplate, StageStatus, pending_items
from revue_portee.reporting.formats import date, integer, separator

__all__ = ["FlowContext", "render_flow_svg"]

type Translate = Callable[[str], str]
type BoxLine = tuple[str, bool, int]  # text, bold, indent

WIDTH = 900
BAND_X, BAND_WIDTH = 10, 28
MAIN_X, MAIN_WIDTH = 50, 420
SIDE_X, SIDE_WIDTH = 530, 360
TOP = 84
ROW_GAP = 36
PADDING = 10
LINE_HEIGHT = 16
NOTE_LINE_HEIGHT = 15
CHAR_WIDTH = 6.4  # average width of a 12 px sans-serif character, generously rounded
NOTE_CHAR_WIDTH = 5.9  # 11 px


@dataclass(frozen=True, slots=True)
class FlowContext:
    """What the diagram says besides its numbers."""

    project_title: str
    criteria_version: int | None
    tool_version: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class Line:
    text: str
    x: float
    y: float
    bold: bool = False


@dataclass(slots=True)
class Box:
    x: float
    width: float
    lines: list[BoxLine]
    later: bool = False
    y: float = 0
    height: float = 0
    text: list[Line] = field(default_factory=list)

    def place(self, y: float) -> None:
        wrapped: list[BoxLine] = []
        for content, bold, indent in self.lines:
            width = int((self.width - 2 * PADDING - indent) / CHAR_WIDTH)
            for part in textwrap.wrap(content, width) or [""]:
                wrapped.append((part, bold, indent))
        self.y = y
        self.height = 2 * PADDING + LINE_HEIGHT * len(wrapped) - 4
        self.text = [
            Line(text, self.x + PADDING + indent, y + PADDING + 12 + LINE_HEIGHT * i, bold)
            for i, (text, bold, indent) in enumerate(wrapped)
        ]

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True, slots=True)
class Arrow:
    x1: float
    y1: float
    x2: float
    y2: float
    later: bool


@dataclass(frozen=True, slots=True)
class Band:
    y: float
    height: float
    label: str

    @property
    def center(self) -> tuple[float, float]:
        return BAND_X + BAND_WIDTH / 2, self.y + self.height / 2


def _n(value: int, language: str) -> str:
    return f"(n = {integer(value, language)})"


def _counted(label: str, value: int, language: str) -> str:
    return f"{label} {_n(value, language)}"


def _rows(
    _: Translate, numbers: FlowNumbers, template: FlowTemplate, language: str
) -> list[tuple[str, Box, Box | None]]:
    """The rows of the diagram: phase, main box, box on the right."""

    def label(box_id: str) -> str:
        return template.box(box_id).label(language)

    def counted(box_id: str, value: int, *, bold: bool = False, indent: int = 0) -> BoxLine:
        return (_counted(label(box_id), value, language), bold, indent)

    def later(main_or_side: tuple[float, float], *box_ids: str) -> Box:
        x, width = main_or_side
        lines = [
            *((label(box_id), False, 0) for box_id in box_ids),
            (_("(stage to come)"), False, 0),
        ]
        return Box(x, width, lines, later=template.box(box_ids[0]).stage is StageStatus.LATER)

    main, side = (MAIN_X, MAIN_WIDTH), (SIDE_X, SIDE_WIDTH)
    screened = counted("screened", numbers.screened, bold=True)
    if numbers.reassessments:
        screened = (screened[0] + "†", True, 0)  # see the note on reassessments
    identified = Box(
        *main,
        [
            (label("identified"), True, 0),
            counted("databases", numbers.identified),
            *(
                (_counted(name, count, language), False, 14)
                for name, count in numbers.identified_by_source.items()
            ),
            counted("registers", numbers.registers),
        ],
    )
    removed = Box(
        *side,
        [
            (label("removed_before_screening"), True, 0),
            counted("duplicates", numbers.duplicates_removed),
            counted("automation", numbers.removed_by_automation),
            counted("other_reasons", numbers.removed_other),
        ],
    )
    excluded = Box(
        *side,
        [
            counted("excluded", numbers.excluded, bold=True),
            counted("excluded_by_person", numbers.excluded_by_person, indent=14),
            counted("excluded_by_automation", numbers.excluded_by_automation, indent=14),
        ],
    )
    identified_row = ("identification", identified, removed)
    screened_row = ("screening", Box(*main, [screened]), excluded)
    sought = Box(*main, [counted("sought", numbers.sought, bold=True)])
    if numbers.not_retrieved is None:
        not_retrieved = later(side, "not_retrieved")
    else:
        not_retrieved = Box(*side, [counted("not_retrieved", numbers.not_retrieved, bold=True)])
    full_text = numbers.full_text
    if full_text is None:
        return [
            identified_row,
            screened_row,
            ("screening", sought, not_retrieved),
            ("screening", later(main, "assessed"), later(side, "reports_excluded")),
            ("included", later(main, "included", "included_reports"), None),
        ]
    colon = " : " if language == "fr" else ": "
    reasons = [
        (_counted(code + colon + full_text.reason_labels[code], n, language), False, 14)
        if full_text.reason_labels.get(code)
        else (_counted(code, n, language), False, 14)
        for code, n in full_text.excluded_by_reason.items()
    ]
    excluded_reports = Box(
        *side, [counted("reports_excluded", full_text.excluded, bold=True), *reasons]
    )
    included = Box(
        *main,
        [
            counted(
                "included",
                full_text.included if full_text.studies is None else full_text.studies,
                bold=True,
            ),
            counted("included_reports", full_text.included),
        ],
    )
    return [
        identified_row,
        screened_row,
        ("screening", sought, not_retrieved),
        ("screening", Box(*main, [counted("assessed", full_text.assessed, bold=True)]),
         excluded_reports),
        ("included", included, None),
    ]  # fmt: skip


def _reassessment_note(_: Translate, numbers: FlowNumbers, language: str) -> str:
    changes = numbers.reassessments
    versions = separator(language).join(
        _("version {before} to {after}").format(before=r.from_version, after=r.to_version)
        for r in changes
    )
    note = _(
        "† Criteria changes during the screening: {count} ({versions}). References "
        "reassessed (AI, then the person for the decisions it would change): {reassessed}; "
        "decisions changed from keep to exclude: {kept_to_excluded}; from exclude to keep: "
        "{excluded_to_kept}. The numbers above take these changes into account."
    ).format(
        count=len(changes),
        versions=versions,
        reassessed=integer(sum(r.reassessed for r in changes), language),
        kept_to_excluded=integer(sum(r.kept_to_excluded for r in changes), language),
        excluded_to_kept=integer(sum(r.excluded_to_kept for r in changes), language),
    )
    unfinished = sum(1 for r in changes if not r.completed)
    if unfinished:
        note += " " + _("Reassessments not completed: {count}.").format(count=unfinished)
    return note


def _pending_note(_: Translate, numbers: FlowNumbers, language: str) -> str:
    items = pending_items(_, numbers.pending, language)
    return _("Provisional diagram: {items}.").format(items=separator(language).join(items))


def _notes(
    _: Translate,
    numbers: FlowNumbers,
    template: FlowTemplate,
    context: FlowContext,
    language: str,
) -> list[str]:
    notes = []
    if numbers.reassessments:
        notes.append(_reassessment_note(_, numbers, language))
    if numbers.provisional:
        notes.append(_pending_note(_, numbers, language))
    elif numbers.excluded_by_automation == 0:
        notes.append(
            _(
                "The AI was the second reviewer of every reference; every exclusion was "
                "decided by a person, none by the AI alone."
            )
        )
    notes.append(
        _(
            "Template: PRISMA 2020 flow diagram for databases and registers (Page et al., "
            "2021), adapted for scoping reviews (PRISMA-ScR, Tricco et al., 2018); {license}."
        ).format(license=template.license)
    )
    generated = _("Generated by revue-portee {version} on {date}").format(
        version=context.tool_version, date=date(context.generated_at)
    )
    if context.criteria_version is not None:
        generated += separator(language) + _("criteria version {number}").format(
            number=context.criteria_version
        )
    notes.append(generated + ".")
    return notes


def _arrows(rows: Sequence[tuple[str, Box, Box | None]]) -> list[Arrow]:
    arrows = []
    center = MAIN_X + MAIN_WIDTH / 2
    for i, (_phase, main, side) in enumerate(rows):
        if side is not None:
            y = main.y + min(main.height, side.height) / 2
            arrows.append(Arrow(MAIN_X + MAIN_WIDTH, y, SIDE_X, y, side.later))
        if i + 1 < len(rows):
            below = rows[i + 1][1]
            arrows.append(Arrow(center, main.bottom, center, below.y, below.later))
    return arrows


def _bands(
    rows: Sequence[tuple[str, Box, Box | None]], template: FlowTemplate, language: str
) -> list[Band]:
    bands: list[Band] = []
    for phase, main, side in rows:
        bottom = max(main.bottom, side.bottom if side else 0)
        label = template.phase(phase).fr if language == "fr" else template.phase(phase).en
        if bands and bands[-1].label == label:
            last = bands[-1]
            bands[-1] = Band(last.y, bottom - last.y, label)
        else:
            bands.append(Band(main.y, bottom - main.y, label))
    return bands


@cache
def _environment() -> Environment:
    return Environment(
        loader=PackageLoader("revue_portee.reporting", "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_flow_svg(
    numbers: FlowNumbers, template: FlowTemplate, context: FlowContext, *, language: str
) -> str:
    """The diagram in ``language`` (fr or en), as an SVG document."""
    _ = translator(language)
    rows = _rows(_, numbers, template, language)
    y: float = TOP
    for _phase, main, side in rows:
        main.place(y)
        if side is not None:
            side.place(y)
        y = max(main.bottom, side.bottom if side else 0) + ROW_GAP
    notes: list[Line] = []
    y += 4
    for note in _notes(_, numbers, template, context, language):
        for part in textwrap.wrap(note, int((WIDTH - 2 * BAND_X) / NOTE_CHAR_WIDTH)):
            notes.append(Line(part, BAND_X, y))
            y += NOTE_LINE_HEIGHT
        y += 4
    height = y + 10
    boxes = [box for _phase, main, side in rows for box in (main, side) if box is not None]
    return (
        _environment()
        .get_template("flow.svg.j2")
        .render(
            language=language,
            width=WIDTH,
            height=height,
            title=_("PRISMA 2020 flow diagram adapted for scoping reviews"),
            project_title=context.project_title,
            boxes=boxes,
            arrows=_arrows(rows),
            bands=_bands(rows, template, language),
            band_x=BAND_X,
            band_width=BAND_WIDTH,
            notes=notes,
            provisional=_("PROVISIONAL") if numbers.provisional else "",
        )
    )
