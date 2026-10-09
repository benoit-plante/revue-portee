"""The person's check of the extracted values, the extraction pilot and the data kept
for the synthesis (EF-EXT-04, EF-EXT-05, tranche 3.3).

Every value the AI proposes is validated, corrected or rejected by the person; a field
the AI did not fill is extracted by the person. Each decision is a new value that
supersedes the previous one (nothing is changed). Only values a person decided go into
the synthesis and the export (``domain.extraction.for_synthesis``).

The pilot draws a few studies with a recorded seed; the person extracts them without
seeing the AI, whose values for a study are shown only once the person has given every
field of it. The agreement of the AI with the person is then measured field by field.
"""

import csv
import io
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import JsonValue

from revue_portee.domain.extraction import (
    ExtractionPilot,
    ExtractionValue,
    ValueStatus,
    current_values,
    for_synthesis,
    holds_value,
    parse_value,
    place_quote,
    same_value,
    stale,
)
from revue_portee.domain.grid import GridField, GridVersion, field_sort_key
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import ReviewerKind
from revue_portee.domain.screening import draw_sample
from revue_portee.extraction.prefill import NoGridError, StudyExtraction, extraction_state
from revue_portee.fulltext import retrieval
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.screening import studies
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import extraction as extraction_repo
from revue_portee.storage.repositories import grid as grid_repo
from revue_portee.storage.repositories import journal

__all__ = [
    "PILOT_SIZE",
    "ArchivedValue",
    "FieldAgreement",
    "NoAIValueError",
    "NotAStudyError",
    "NothingToConfirmError",
    "PilotState",
    "SynthesisRow",
    "archived_values",
    "blind",
    "confirm_value",
    "export_extraction",
    "pilot_state",
    "record_value",
    "reject_value",
    "start_pilot",
    "synthesis_rows",
    "validate_value",
]

Clock = Callable[[], datetime]
PILOT_SIZE = 5


class NotAStudyError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("Unknown study or field."))


class NoAIValueError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("There is no value of the AI to check on this field."))


def _study(
    folder: ProjectFolder, reference_id: str, field_code: str
) -> tuple[GridVersion, GridField]:
    state = extraction_state(folder)
    if state.grid is None:
        raise NoGridError
    grid_field = state.grid.field(field_code)
    if grid_field is None or reference_id not in {s.primary.id for s in state.studies}:
        raise NotAStudyError
    return state.grid, grid_field


def _current(folder: ProjectFolder, reference_id: str, field_code: str) -> ExtractionValue | None:
    with folder.engine.connect() as connection:
        values = extraction_repo.list_values(connection, reference_id=reference_id)
    return current_values(values).get((reference_id, field_code))


def _record(
    folder: ProjectFolder,
    value: ExtractionValue,
    summary: str,
    *,
    tool_version: str,
) -> ExtractionValue:
    with folder.write() as connection:
        entry = journal.append_entry(
            connection,
            now=value.created_at,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.EXTRACTION_VALUE_DECIDED,
            subject_type="extraction_value",
            subject_id=value.id,
            summary_fr=summary,
            tool_version=tool_version,
            payload={
                "reference": value.reference_id,
                "field": value.field_code,
                "status": value.status.value,
                "reported": value.reported,
                "value": value.value,
                "supersedes": value.supersedes_id,
            },
        )
        extraction_repo.insert_value(connection, value, journal_entry_id=entry.id)
    return value


def _ai_value(folder: ProjectFolder, reference_id: str, field_code: str) -> ExtractionValue:
    current = _current(folder, reference_id, field_code)
    if (
        current is None
        or current.reviewer_kind is not ReviewerKind.AI
        or blind(folder, reference_id)
    ):
        raise NoAIValueError
    return current


def validate_value(
    folder: ProjectFolder, reference_id: str, field_code: str, *, note: str = "", now: Clock,
    tool_version: str,
) -> ExtractionValue:  # fmt: skip
    """Keep the AI's value: the person's validation is a new value, equal to it."""
    grid, _field = _study(folder, reference_id, field_code)
    ai = _ai_value(folder, reference_id, field_code)
    moment = now()
    value = ai.model_copy(
        update={
            "id": new_ulid(moment),
            "grid_version_id": grid.id,  # validated under the field in force
            "status": ValueStatus.VALIDATED,
            "reviewer_id": folder.reviewer_id,
            "reviewer_kind": ReviewerKind.HUMAN,
            "supersedes_id": ai.id,
            "ai_call_id": None,
            "note": note.strip(),
            "created_at": moment,
        }
    )
    return _record(
        folder, value, french("Extraction: value of {field} validated").format(field=field_code),
        tool_version=tool_version,
    )  # fmt: skip


class NothingToConfirmError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("There is no value of yours to confirm on this field."))


def confirm_value(
    folder: ProjectFolder, reference_id: str, field_code: str, *, note: str = "", now: Clock,
    tool_version: str,
) -> ExtractionValue:  # fmt: skip
    """Keep a value the person gave under a former definition of its field: a new value,
    equal to it, given under the grid in force (tranche 3.4)."""
    grid, grid_field = _study(folder, reference_id, field_code)
    current = _current(folder, reference_id, field_code)
    if (
        current is None
        or current.reviewer_kind is not ReviewerKind.HUMAN
        or not holds_value(current)
        or not stale(current, _versions(folder), grid_field)
    ):
        raise NothingToConfirmError
    moment = now()
    value = current.model_copy(
        update={
            "id": new_ulid(moment),
            "grid_version_id": grid.id,
            "reviewer_id": folder.reviewer_id,
            "supersedes_id": current.id,
            "note": note.strip() or current.note,
            "created_at": moment,
        }
    )
    summary = french("Extraction: value of {field} confirmed under the field in force")
    return _record(folder, value, summary.format(field=field_code), tool_version=tool_version)


def reject_value(
    folder: ProjectFolder, reference_id: str, field_code: str, *, note: str = "", now: Clock,
    tool_version: str,
) -> ExtractionValue:  # fmt: skip
    """Reject the AI's value without giving another: the field has no value."""
    grid, _field = _study(folder, reference_id, field_code)
    ai = _ai_value(folder, reference_id, field_code)
    moment = now()
    value = ExtractionValue(
        id=new_ulid(moment), reference_id=reference_id, field_code=field_code,
        grid_version_id=grid.id, reported=False, status=ValueStatus.REJECTED,
        reviewer_id=folder.reviewer_id, reviewer_kind=ReviewerKind.HUMAN, supersedes_id=ai.id,
        note=note.strip(), created_at=moment,
    )  # fmt: skip
    return _record(
        folder, value, french("Extraction: value of {field} rejected").format(field=field_code),
        tool_version=tool_version,
    )  # fmt: skip


def record_value(
    folder: ProjectFolder,
    reference_id: str,
    field_code: str,
    *,
    reported: bool,
    value: JsonValue = None,
    quote: str = "",
    page: int | None = None,
    note: str = "",
    now: Clock,
    tool_version: str,
) -> ExtractionValue:
    """The person's own value of a field: a correction of the AI's value, or an
    extraction where the AI gave none (and in the pilot, where it is not shown).
    The value is checked against its field; a quote is looked for in the text."""
    grid, grid_field = _study(folder, reference_id, field_code)
    parsed = parse_value(grid_field, value) if reported else None
    current = _current(folder, reference_id, field_code)
    corrects = (
        current is not None
        and current.reviewer_kind is ReviewerKind.AI
        and not blind(folder, reference_id)
    )
    quote = quote.strip() if reported else ""
    shown_page, check = None, None
    if quote:
        document = studies.included_reports(folder)[reference_id][1]
        if not document.needs_ocr:
            body = retrieval.paged_text(folder, document).body()
            shown_page, check = place_quote(body, quote, page)
        else:
            shown_page = page
    moment = now()
    recorded = ExtractionValue(
        id=new_ulid(moment), reference_id=reference_id, field_code=field_code,
        grid_version_id=grid.id, reported=reported, value=parsed, quote=quote, page=shown_page,
        model_page=None, quote_check=check,
        status=ValueStatus.CORRECTED if corrects else ValueStatus.EXTRACTED,
        reviewer_id=folder.reviewer_id, reviewer_kind=ReviewerKind.HUMAN,
        supersedes_id=None if current is None else current.id, note=note.strip(),
        created_at=moment,
    )  # fmt: skip
    if corrects:
        summary = french("Extraction: value of {field} corrected")
    else:
        summary = french("Extraction: value of {field} extracted by the person")
    return _record(folder, recorded, summary.format(field=field_code), tool_version=tool_version)


# --- Pilot --------------------------------------------------------------------------


def _pilots(folder: ProjectFolder) -> list[ExtractionPilot]:
    with folder.engine.connect() as connection:
        return extraction_repo.list_pilots(connection)


def blind(folder: ProjectFolder, reference_id: str) -> bool:
    """Whether the AI's values of the study are hidden from the person: the study is
    in the latest pilot and the person has not given every field of it yet."""
    state = pilot_state(folder)
    return (
        state is not None
        and reference_id in state.pilot.reference_ids
        and not state.complete(reference_id)
    )


def start_pilot(
    folder: ProjectFolder,
    *,
    size: int = PILOT_SIZE,
    seed: int | None = None,
    now: Clock,
    tool_version: str,
) -> ExtractionPilot:
    """Draw the studies of an extraction pilot (every study when there are fewer)."""
    state = extraction_state(folder)
    if state.grid is None:
        raise NoGridError
    population = [s.primary.id for s in state.studies]
    if not population:
        raise NotAStudyError
    drawn_seed = secrets.randbelow(2**31) if seed is None else seed
    sample = draw_sample(population, min(size, len(population)), drawn_seed)
    moment = now()
    pilot = ExtractionPilot(
        id=new_ulid(moment), number=len(_pilots(folder)) + 1, seed=drawn_seed,
        grid_version_id=state.grid.id, reference_ids=sample, created_at=moment,
        reviewer_id=folder.reviewer_id,
    )  # fmt: skip
    with folder.write() as connection:
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.EXTRACTION_PILOT_STARTED,
            subject_type="extraction_pilot",
            subject_id=pilot.id,
            summary_fr=french(
                "Extraction pilot {number}: studies drawn: {size} of {population} (seed {seed})"
            ).format(
                number=pilot.number, size=len(sample), population=len(population), seed=drawn_seed
            ),
            tool_version=tool_version,
            payload={
                "seed": drawn_seed,
                "reference_ids": list(sample),
                "grid_version": state.grid.number,
            },
        )
        extraction_repo.insert_pilot(connection, pilot, journal_entry_id=entry.id)
    return pilot


@dataclass
class FieldAgreement:
    code: str
    label: str
    compared: int = 0
    agreed: int = 0

    @property
    def share(self) -> float | None:
        return self.agreed / self.compared if self.compared else None


@dataclass(frozen=True, slots=True)
class PilotState:
    pilot: ExtractionPilot
    human: dict[str, dict[str, ExtractionValue]]  # by study, then field: the person's
    ai: dict[str, dict[str, ExtractionValue]]  # by study, then field: the AI's
    fields: tuple[GridField, ...]
    agreement: list[FieldAgreement] = field(default_factory=list)

    def complete(self, reference_id: str) -> bool:
        """Every field of the study given by the person."""
        given = self.human.get(reference_id, {})
        return all(f.code in given for f in self.fields)

    def visible_ai(self, reference_id: str) -> dict[str, ExtractionValue]:
        """The AI's values, only once the person has given every field (blind)."""
        return self.ai.get(reference_id, {}) if self.complete(reference_id) else {}

    @property
    def done(self) -> int:
        return sum(1 for ref in self.pilot.reference_ids if self.complete(ref))


def pilot_state(folder: ProjectFolder) -> PilotState | None:
    """The latest extraction pilot, with the agreement of the AI with the person."""
    pilots = _pilots(folder)
    if not pilots:
        return None
    pilot = pilots[-1]
    state = extraction_state(folder)
    grid = state.grid
    fields = () if grid is None else grid.sorted_fields()
    with folder.engine.connect() as connection:
        stored = extraction_repo.list_values(connection)
    values = [v for v in stored if v.reference_id in pilot.reference_ids]
    versions = _versions(folder)
    by_code = {f.code: f for f in fields}
    human: dict[str, dict[str, ExtractionValue]] = {}
    ai: dict[str, dict[str, ExtractionValue]] = {}
    for value in sorted(values, key=lambda v: (v.created_at, v.id)):
        grid_field = by_code.get(value.field_code)
        if grid_field is None or stale(value, versions, grid_field):
            continue  # compared only under the field in force
        target = ai if value.reviewer_kind is ReviewerKind.AI else human
        target.setdefault(value.reference_id, {})[value.field_code] = value
    result = PilotState(pilot=pilot, human=human, ai=ai, fields=fields)
    agreement = {f.code: FieldAgreement(f.code, f.label) for f in fields}
    for ref in pilot.reference_ids:
        if not result.complete(ref):
            continue
        for grid_field in fields:
            ai_value = ai.get(ref, {}).get(grid_field.code)
            if ai_value is None:
                continue
            score = agreement[grid_field.code]
            score.compared += 1
            score.agreed += same_value(grid_field, human[ref][grid_field.code], ai_value)
    return PilotState(
        pilot=pilot, human=human, ai=ai, fields=fields, agreement=list(agreement.values())
    )


# --- Data for the synthesis ---------------------------------------------------------


def _shown(value: JsonValue) -> str:
    if value is True:
        return "oui"
    if value is False:
        return "non"
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    return "" if value is None else str(value)


@dataclass(frozen=True, slots=True)
class SynthesisRow:
    study: StudyExtraction
    field: GridField
    value: ExtractionValue | None  # the value a person decided, None when no one did yet
    to_review: bool  # given under another definition of the field (tranche 3.4)


def _versions(folder: ProjectFolder) -> dict[str, GridVersion]:
    with folder.engine.connect() as connection:
        return {v.id: v for v in grid_repo.list_versions(connection)}


def synthesis_rows(folder: ProjectFolder) -> list[SynthesisRow]:
    """For each study and each field of the grid in force, the value a person decided:
    only these go into the synthesis (EF-EXT-04)."""
    state = extraction_state(folder)
    if state.grid is None:
        return []
    with folder.engine.connect() as connection:
        kept = for_synthesis(extraction_repo.list_values(connection))
    versions = _versions(folder)
    rows = []
    for study in state.studies:
        for grid_field in state.grid.sorted_fields():
            value = kept.get((study.primary.id, grid_field.code))
            rows.append(
                SynthesisRow(
                    study=study,
                    field=grid_field,
                    value=value,
                    to_review=value is not None and stale(value, versions, grid_field),
                )
            )
    return rows


@dataclass(frozen=True, slots=True)
class ArchivedValue:
    study: StudyExtraction
    label: str  # the label of the field when the value was given
    value: ExtractionValue


def archived_values(folder: ProjectFolder) -> list[ArchivedValue]:
    """The values in force on fields removed from the grid: out of the synthesis, kept
    recorded (EF-VER-06)."""
    state = extraction_state(folder)
    if state.grid is None:
        return []
    versions = _versions(folder)
    in_force = {f.code for f in state.grid.fields}
    found = []
    for study in state.studies:
        for code, value in sorted(study.values.items(), key=lambda kv: field_sort_key(kv[0])):
            if code in in_force or not holds_value(value):
                continue
            made = versions.get(value.grid_version_id)
            old = None if made is None else made.field(code)
            found.append(ArchivedValue(study, code if old is None else old.label, value))
    return found


def _write(path: Path, header: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buffer.getvalue(), encoding="utf-8")


def _cells(value: ExtractionValue | None) -> tuple[object, ...]:
    if value is None:
        return ("", "", "", "")
    return (
        "oui" if value.reported else "non",
        _shown(value.value),
        "" if value.page is None else value.page,
        value.status.value,
    )


def export_extraction(folder: ProjectFolder) -> tuple[Path, int]:
    """Write ``exports/donnees-extraites.csv``: the values a person decided, one row per
    study and field (empty when no one did yet), flagged when given under another
    definition of the field; and, when fields were removed, their archived values in
    ``exports/donnees-archivees.csv``. Returns the first file and the values written."""
    rows = synthesis_rows(folder)
    target = folder.path / "exports" / "donnees-extraites.csv"
    _write(
        target,
        ("study", "title", "year", "field", "label", "reported", "value", "page", "status",
         "to_review"),
        [
            (r.study.primary.id, r.study.primary.title, r.study.primary.year or "", r.field.code,
             r.field.label, *_cells(r.value), "oui" if r.to_review else "")
            for r in rows
        ],
    )  # fmt: skip
    archived = archived_values(folder)
    if archived:
        _write(
            folder.path / "exports" / "donnees-archivees.csv",
            ("study", "title", "year", "field", "label", "reported", "value", "page", "status"),
            [
                (a.study.primary.id, a.study.primary.title, a.study.primary.year or "",
                 a.value.field_code, a.label, *_cells(a.value))
                for a in archived
            ],
        )  # fmt: skip
    return target, sum(1 for r in rows if r.value is not None)
