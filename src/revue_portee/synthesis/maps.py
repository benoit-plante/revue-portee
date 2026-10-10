"""Tables, evidence maps and gaps of the synthesis (EF-SYN-01 to EF-SYN-03, tranche 3.5).

Built from the values a person decided only (EF-EXT-04), on the fields of the grid in
force. The person comments the gaps of a map; each comment is journaled and a new one
replaces the previous. Exports are written in ``exports/synthese/``.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from revue_portee.domain.extraction import for_synthesis
from revue_portee.domain.grid import GridField, GridVersion
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.references import Reference
from revue_portee.domain.synthesis import GapComment, latest_comments
from revue_portee.extraction.prefill import NoGridError, extraction_state
from revue_portee.i18n import french, translator
from revue_portee.i18n import gettext as _
from revue_portee.reporting.synthesis import (
    CategoryLabels,
    CrossTable,
    FrequencyTable,
    StudyData,
    cross_table,
    frequency_table,
    gaps,
)
from revue_portee.reporting.synthesis_export import (
    MapContext,
    cross_csv,
    cross_markdown,
    frequency_csv,
    frequency_markdown,
    map_html,
    map_svg,
    tables_xlsx,
)
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import extraction as extraction_repo
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import synthesis as synthesis_repo

__all__ = [
    "SPARSE_MAX",
    "UnknownFieldError",
    "category_labels",
    "comment_gap",
    "comments",
    "cross",
    "export_map",
    "export_tables",
    "frequencies",
    "study_data",
    "study_label",
]

Clock = Callable[[], datetime]
SPARSE_MAX = 1


class UnknownFieldError(LookupError):
    def __init__(self, code: str) -> None:
        super().__init__(_("Unknown field: {code}.").format(code=code))


def category_labels(language: str) -> CategoryLabels:
    translate = translator(language)
    return CategoryLabels(yes=translate("yes"), no=translate("no"))


def study_label(reference: Reference) -> str:
    """First author's surname and year, otherwise the title."""
    if reference.authors:
        surname = reference.authors[0].split(",")[0].strip()
        others = " et al." if len(reference.authors) > 1 else ""
        return f"{surname}{others} {reference.year or 's. d.'}".strip()
    return reference.title or reference.id


def study_data(folder: ProjectFolder) -> tuple[GridVersion, list[StudyData]]:
    """The grid in force and, for each included study, the values a person decided."""
    state = extraction_state(folder)
    if state.grid is None:
        raise NoGridError
    with folder.engine.connect() as connection:
        kept = for_synthesis(
            extraction_repo.list_values(connection), replication=folder.replication is not None
        )
    codes = {f.code for f in state.grid.fields}
    found = []
    for study in state.studies:
        decided = {
            code: value
            for (ref, code), value in kept.items()
            if ref == study.primary.id and code in codes
        }
        found.append(
            StudyData(
                id=study.primary.id,
                label=study_label(study.primary),
                values={c: v.value for c, v in decided.items() if v.reported},
                not_reported=frozenset(c for c, v in decided.items() if not v.reported),
            )
        )
    return state.grid, found


def frequencies(folder: ProjectFolder, *, language: str = "fr") -> list[FrequencyTable]:
    grid, studies = study_data(folder)
    labels = category_labels(language)
    return [frequency_table(f, studies, labels) for f in grid.sorted_fields()]


def _field(grid: GridVersion, code: str) -> GridField:
    found = grid.field(code)
    if found is None:
        raise UnknownFieldError(code)
    return found


def cross(
    folder: ProjectFolder, rows: str, columns: str, *, language: str = "fr"
) -> tuple[CrossTable, list[StudyData]]:
    grid, studies = study_data(folder)
    table = cross_table(
        _field(grid, rows), _field(grid, columns), studies, category_labels(language)
    )
    return table, studies


def comments(folder: ProjectFolder, rows: str, columns: str) -> dict[tuple[str, str], str]:
    with folder.engine.connect() as connection:
        return latest_comments(synthesis_repo.list_comments(connection), rows, columns)


def comment_gap(
    folder: ProjectFolder,
    rows: str,
    columns: str,
    row: str,
    column: str,
    text: str,
    *,
    now: Clock,
    tool_version: str,
) -> GapComment:
    """Comment one cell of the map of ``rows`` by ``columns`` (empty: withdraw)."""
    table, _studies = cross(folder, rows, columns)
    if row not in table.rows or column not in table.columns:
        raise UnknownFieldError(f"{row} / {column}")
    moment = now()
    comment = GapComment(
        id=new_ulid(moment), rows_field=rows, columns_field=columns, row=row, column=column,
        text=text.strip(), created_at=moment, reviewer_id=folder.reviewer_id,
    )  # fmt: skip
    with folder.write() as connection:
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SYNTHESIS_GAP_COMMENTED,
            subject_type="gap_comment",
            subject_id=comment.id,
            summary_fr=french("Evidence map {rows} by {columns}: gap commented").format(
                rows=rows, columns=columns
            ),
            tool_version=tool_version,
            payload={
                "rows_field": rows,
                "columns_field": columns,
                "row": row,
                "column": column,
                "text": comment.text,
            },
        )
        synthesis_repo.insert_comment(connection, comment, journal_entry_id=entry.id)
    return comment


def _in(language: str, text: str) -> str:
    """A title of the exports, in their language."""
    _ = translator(language)
    return {"tables": _("Synthesis tables")}[text]


def _target(folder: ProjectFolder) -> Path:
    target = folder.path / "exports" / "synthese"
    target.mkdir(parents=True, exist_ok=True)
    return target


def export_tables(
    folder: ProjectFolder,
    *,
    language: str,
    crosses: Sequence[tuple[str, str]] = (),
    now: Clock,
) -> list[Path]:
    """Frequency tables of every field (and the cross tables asked) in CSV, Markdown
    and XLSX."""
    tables = frequencies(folder, language=language)
    cross_tables = [cross(folder, r, c, language=language)[0] for r, c in crosses]
    target = _target(folder)
    written = []
    for table in tables:
        path = target / f"frequences-{table.field.code}-{language}.csv"
        path.write_text(frequency_csv(table, language), encoding="utf-8")
        written.append(path)
    for crossed in cross_tables:
        name = f"croise-{crossed.rows_field.code}-{crossed.columns_field.code}-{language}.csv"
        path = target / name
        path.write_text(cross_csv(crossed, language), encoding="utf-8")
        written.append(path)
    markdown = target / f"tableaux-{language}.md"
    with folder.engine.connect() as connection:
        title = projects.get_project(connection).title
    heading = _in(language, "tables")
    markdown.write_text(
        f"# {heading} — {title}\n\n"
        + "\n".join(frequency_markdown(t, language) for t in tables)
        + "".join("\n" + cross_markdown(t, language) for t in cross_tables),
        encoding="utf-8",
    )
    xlsx = target / f"tableaux-{language}.xlsx"
    xlsx.write_bytes(tables_xlsx(tables, cross_tables, language=language, generated_at=now()))
    return [*written, markdown, xlsx]


def export_map(
    folder: ProjectFolder,
    rows: str,
    columns: str,
    *,
    language: str,
    sparse_max: int = SPARSE_MAX,
    now: Clock,
    tool_version: str,
) -> list[Path]:
    """The evidence map of ``rows`` by ``columns``: SVG image, HTML page and its cross
    table in CSV."""
    table, studies = cross(folder, rows, columns, language=language)
    found = gaps(table, sparse_max=sparse_max)
    with folder.engine.connect() as connection:
        title = projects.get_project(connection).title
    context = MapContext(
        project_title=title, language=language, tool_version=tool_version, generated_at=now()
    )
    target = _target(folder)
    stem = f"carte-{rows}-{columns}-{language}"
    svg = target / f"{stem}.svg"
    svg.write_text(map_svg(table, found, context), encoding="utf-8")
    page = target / f"{stem}.html"
    labels = {s.id: s.label for s in studies}
    page.write_text(
        map_html(table, found, labels, comments(folder, rows, columns), context),
        encoding="utf-8",
    )
    table_csv = target / f"croise-{rows}-{columns}-{language}.csv"
    table_csv.write_text(cross_csv(table, language), encoding="utf-8")
    return [svg, page, table_csv]
