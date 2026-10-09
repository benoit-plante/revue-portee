"""Exports of the synthesis tables and of the evidence map (EF-SYN-01, EF-SYN-02).

Tables in CSV, Markdown and XLSX; the map as an SVG image and as a self-contained HTML
page (the image, the studies of each cell and the gaps with their comments), in French
or English. The output is deterministic: the same data give the same files (the XLSX
carries the generation date as its creation date).
"""

import csv
import html
import io
import math
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font

from revue_portee.i18n import translator
from revue_portee.reporting.formats import date, percent
from revue_portee.reporting.synthesis import CrossTable, FrequencyTable, Gap, GapKind

__all__ = [
    "MapContext",
    "cross_csv",
    "cross_markdown",
    "frequency_csv",
    "frequency_markdown",
    "map_html",
    "map_svg",
    "tables_xlsx",
]

type Translate = Callable[[str], str]
type Grid = list[list[str | int]]
TIMES = chr(0xD7)  # multiplication sign, between the two fields of a cross table


def escape(text: str) -> str:
    """Escape the text of an element (every escaped text here is element content)."""
    return html.escape(text, quote=False)


@dataclass(frozen=True, slots=True)
class MapContext:
    project_title: str
    language: str
    tool_version: str
    generated_at: datetime


# --- Tables ---------------------------------------------------------------------------


def _frequency_grid(table: FrequencyTable, language: str) -> Grid:
    _ = translator(language)
    grid: Grid = [[_("Category"), _("Studies"), _("Share of the included studies")]]
    for row in table.rows:
        share = table.share(row)
        grid.append([row.category, row.count, "" if share is None else percent(share, language)])
    grid.append([_("Not reported"), len(table.not_reported), ""])
    grid.append([_("Not extracted yet"), len(table.not_extracted), ""])
    grid.append([_("Included studies"), table.total, ""])
    return grid


def _cross_grid(table: CrossTable, language: str) -> Grid:
    _ = translator(language)
    corner = f"{table.rows_field.label} \\ {table.columns_field.label}"
    grid: Grid = [[corner, *table.columns, _("Total")]]
    for row in table.rows:
        counts = [table.count(row, column) for column in table.columns]
        placed = {s for column in table.columns for s in table.studies(row, column)}
        grid.append([row, *counts, len(placed)])
    totals = [
        len({s for row in table.rows for s in table.studies(row, column)})
        for column in table.columns
    ]
    grid.append([_("Total"), *totals, len(table.placed)])
    return grid


def _csv(grid: Grid) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(grid)
    return buffer.getvalue()


def _markdown(grid: Grid) -> str:
    def cell(value: str | int) -> str:
        return str(value).replace("|", "\\|")

    head, *body = grid
    lines = [
        "| " + " | ".join(cell(v) for v in head) + " |",
        "|" + "---|" * len(head),
        *("| " + " | ".join(cell(v) for v in row) + " |" for row in body),
    ]
    return "\n".join(lines) + "\n"


def frequency_csv(table: FrequencyTable, language: str) -> str:
    return _csv(_frequency_grid(table, language))


def cross_csv(table: CrossTable, language: str) -> str:
    return _csv(_cross_grid(table, language))


def frequency_markdown(table: FrequencyTable, language: str) -> str:
    _ = translator(language)
    title = f"## {table.field.code} — {table.field.label}\n\n"
    note = _("A study counts once in each of its categories; shares are of all included studies.")
    return title + _markdown(_frequency_grid(table, language)) + f"\n{note}\n"


def cross_markdown(table: CrossTable, language: str) -> str:
    _ = translator(language)
    title = (
        f"## {table.rows_field.code} {TIMES} {table.columns_field.code} — "
        f"{table.rows_field.label} {TIMES} {table.columns_field.label}\n\n"
    )
    note = _("Studies without a value on either field: {count}.").format(count=len(table.unplaced))
    return title + _markdown(_cross_grid(table, language)) + f"\n{note}\n"


def tables_xlsx(
    frequencies: Sequence[FrequencyTable],
    crosses: Sequence[CrossTable],
    *,
    language: str,
    generated_at: datetime,
) -> bytes:
    """One sheet per table: frequencies by field code, cross tables as « D3 x D4 »."""
    book = Workbook()
    book.remove(book.active)  # type: ignore[arg-type]
    book.properties.created = generated_at.replace(tzinfo=None)
    book.properties.modified = generated_at.replace(tzinfo=None)
    book.properties.creator = "revue-portee"
    sheets: list[tuple[str, str, Grid]] = [
        (t.field.code, f"{t.field.code} — {t.field.label}", _frequency_grid(t, language))
        for t in frequencies
    ] + [
        (
            f"{t.rows_field.code} x {t.columns_field.code}",
            f"{t.rows_field.label} {TIMES} {t.columns_field.label}",
            _cross_grid(t, language),
        )
        for t in crosses
    ]
    for name, title, grid in sheets:
        sheet = book.create_sheet(name[:31])
        sheet.append([title])
        sheet["A1"].font = Font(bold=True)
        for row in grid:
            sheet.append(list(row))
        for cell in sheet[2]:
            cell.font = Font(bold=True)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


# --- Evidence map ---------------------------------------------------------------------

CELL_W, CELL_H = 96, 64
LEFT, TOP = 190, 120
MAX_R = 26
CHAR_W = 6.4


def _wrapped(text: str, width: float) -> list[str]:
    return textwrap.wrap(text, max(4, int(width / CHAR_W))) or [""]


def map_svg(table: CrossTable, found_gaps: Sequence[Gap], context: MapContext) -> str:
    """The cross table as a grid of circles whose area follows the number of studies;
    empty cells dashed, sparse cells outlined."""
    _ = translator(context.language)
    kinds = {(g.row, g.column): g.kind for g in found_gaps}
    width = LEFT + CELL_W * max(1, len(table.columns)) + 20
    height = TOP + CELL_H * max(1, len(table.rows)) + 70
    largest = table.largest
    axes = _("Rows: {rows}; columns: {columns}").format(
        rows=f"{table.rows_field.code} {table.rows_field.label}",
        columns=f"{table.columns_field.code} {table.columns_field.label}",
    )
    legend = _("Circle area: number of studies. Shaded cell: no study. Red outline: few studies.")
    placed = _("Studies placed: {placed}; without a value on either field: {unplaced}.").format(
        placed=len(table.placed), unplaced=len(table.unplaced)
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="12" role="img">',
        f"<title>{escape(_('Evidence map'))} — {escape(table.rows_field.label)} {TIMES} "
        f"{escape(table.columns_field.label)}</title>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="10" y="22" font-size="15" font-weight="bold">{escape(_("Evidence map"))}'
        f" — {escape(context.project_title)}</text>",
        f'<text x="10" y="42">{escape(axes)}</text>',
    ]
    for j, column in enumerate(table.columns):
        x = LEFT + j * CELL_W + CELL_W / 2
        lines = _wrapped(column, CELL_W - 6)[:4]
        for k, line in enumerate(lines):
            top = TOP - 8 - (len(lines) - 1 - k) * 14
            parts.append(f'<text x="{x:.1f}" y="{top}" text-anchor="middle">{escape(line)}</text>')
    for i, row in enumerate(table.rows):
        y0 = TOP + i * CELL_H
        lines = _wrapped(row, LEFT - 16)[:3]
        for k, line in enumerate(lines):
            y = y0 + CELL_H / 2 + 4 + (k - (len(lines) - 1) / 2) * 14
            parts.append(
                f'<text x="{LEFT - 8}" y="{y:.1f}" text-anchor="end">{escape(line)}</text>'
            )
        for j, column in enumerate(table.columns):
            x0 = LEFT + j * CELL_W
            kind = kinds.get((row, column))
            fill = "#fbeaea" if kind is GapKind.EMPTY else "#ffffff"
            dash = ' stroke-dasharray="4 3"' if kind is GapKind.EMPTY else ""
            parts.append(
                f'<rect x="{x0}" y="{y0}" width="{CELL_W}" height="{CELL_H}" fill="{fill}" '
                f'stroke="#9aa3ad"{dash}/>'
            )
            count = table.count(row, column)
            if count and largest:
                radius = MAX_R * math.sqrt(count / largest)
                stroke = ' stroke="#c0392b" stroke-width="2"' if kind is GapKind.SPARSE else ""
                parts.append(
                    f'<circle cx="{x0 + CELL_W / 2}" cy="{y0 + CELL_H / 2}" r="{radius:.1f}" '
                    f'fill="#2e6da4" fill-opacity="0.75"{stroke}/>'
                )
                parts.append(
                    f'<text x="{x0 + CELL_W / 2}" y="{y0 + CELL_H / 2 + 4}" text-anchor="middle" '
                    f'font-weight="bold" fill="{"#ffffff" if radius >= 9 else "#1a1a1a"}">'
                    f"{count}</text>"
                )
    legend_y = TOP + CELL_H * max(1, len(table.rows)) + 24
    parts.append(f'<text x="10" y="{legend_y}">{escape(legend)}</text>')
    parts.append(
        f'<text x="10" y="{legend_y + 18}" font-size="11" fill="#555555">{escape(placed)} — '
        f"revue-portee {escape(context.tool_version)}, {date(context.generated_at)}</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def map_html(
    table: CrossTable,
    found_gaps: Sequence[Gap],
    labels: Mapping[str, str],
    comments: Mapping[tuple[str, str], str],
    context: MapContext,
) -> str:
    """A self-contained page: the map, the studies of each cell, the gaps and their
    comments. ``labels`` gives each study's label by id."""
    _ = translator(context.language)
    title = f"{_('Evidence map')} — {table.rows_field.label} {TIMES} {table.columns_field.label}"
    cells = []
    for row in table.rows:
        for column in table.columns:
            ids = table.studies(row, column)
            if ids:
                names = "; ".join(escape(labels.get(i, i)) for i in ids)
                cells.append(
                    f"<tr><td>{escape(row)}</td><td>{escape(column)}</td><td>{len(ids)}</td>"
                    f"<td>{names}</td></tr>"
                )
    kind_labels = {GapKind.EMPTY: _("no study"), GapKind.SPARSE: _("few studies")}
    gap_rows = [
        f"<tr><td>{escape(g.row)}</td><td>{escape(g.column)}</td>"
        f"<td>{escape(kind_labels[g.kind])} ({g.count})</td>"
        f"<td>{escape(comments.get((g.row, g.column), ''))}</td></tr>"
        for g in found_gaps
    ]
    return "\n".join(
        [
            "<!doctype html>",
            f'<html lang="{context.language}">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(title)}</title>",
            "<style>body{font-family:Arial,Helvetica,sans-serif;margin:16px;color:#1a1a1a;"
            "background:#fff}table{border-collapse:collapse;margin:1em 0}td,th{border:1px "
            "solid #9aa3ad;padding:4px 8px;text-align:left;vertical-align:top}"
            ".map{overflow-x:auto}</style>",
            "</head>",
            "<body>",
            f"<h1>{escape(title)}</h1>",
            f"<p>{escape(context.project_title)} — revue-portee {escape(context.tool_version)}, "
            f"{date(context.generated_at)}</p>",
            f'<div class="map">{map_svg(table, found_gaps, context)}</div>',
            f"<h2>{escape(_('Studies by cell'))}</h2>",
            f"<table><thead><tr><th>{escape(table.rows_field.label)}</th>"
            f"<th>{escape(table.columns_field.label)}</th><th>{escape(_('Studies'))}</th>"
            f"<th>{escape(_('Included studies'))}</th></tr></thead><tbody>",
            *cells,
            "</tbody></table>",
            f"<h2>{escape(_('Gaps'))}</h2>",
            f"<table><thead><tr><th>{escape(table.rows_field.label)}</th>"
            f"<th>{escape(table.columns_field.label)}</th><th>{escape(_('Gap'))}</th>"
            f"<th>{escape(_('Comment'))}</th></tr></thead><tbody>",
            *gap_rows,
            "</tbody></table>",
            "</body>",
            "</html>",
            "",
        ]
    )
