"""Local web application (FastAPI + Jinja2 + HTMX), French interface.

The server only answers on 127.0.0.1 (ENF-SEC-06). Because any web page open in the
browser could still send requests to it, every form carries a per-process token and
requests with a foreign ``Host`` or ``Origin`` are refused (CSRF, DNS rebinding).
"""

import re
import secrets
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from importlib.resources import files
from typing import Annotated, Any
from urllib.parse import urlencode, urlsplit

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from pydantic import JsonValue, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from revue_portee.ai.costs import UnknownPriceError
from revue_portee.ai.providers import ProviderFactory, UnknownProviderError
from revue_portee.ai.providers.anthropic import UnsupportedParameterError
from revue_portee.ai.settings import TaskNotAvailableError
from revue_portee.clock import utc_now
from revue_portee.collect import collection, deduplication, enrichment, imports
from revue_portee.collect.collection import CollectorFactory
from revue_portee.collect.enrichment import WorkSource, enriched_reference
from revue_portee.config.secrets import MissingSecretError
from revue_portee.domain.changes import MODIFICATION_TYPES, ChangeType
from revue_portee.domain.criteria import (
    CriterionKind,
    EmptyCriteriaError,
    MissingRationaleError,
    PccElement,
    VersionStatus,
    diff_versions,
)
from revue_portee.domain.dedup import DedupSettings, PairOutcome
from revue_portee.domain.extraction import InvalidValueError
from revue_portee.domain.framing import Framing
from revue_portee.domain.fulltext import FulltextDocument
from revue_portee.domain.grid import FieldType
from revue_portee.domain.grid import diff_versions as grid_diff
from revue_portee.domain.journal import verify_chain
from revue_portee.domain.narrative import NarrativeSentence, UnsupportedSentenceError
from revue_portee.domain.project import ReviewerKind
from revue_portee.domain.protocol import FREE_TEXT_SECTIONS, ProtocolSection, ProtocolText
from revue_portee.domain.screening import (
    DecisionValue,
    RoundKind,
    ScreeningMode,
    ScreeningRound,
    Stage,
    Thresholds,
)
from revue_portee.domain.search import LANGUAGES, BlockRole, Database, WarningKind
from revue_portee.domain.sensitivity import LIMITS
from revue_portee.domain.studies import LinkOutcome, same_pair
from revue_portee.domain.suggestions import SuggestionKind, SuggestionOutcome
from revue_portee.extraction import grid as extraction_grid
from revue_portee.extraction import impact as extraction_impact
from revue_portee.extraction import prefill, validation
from revue_portee.fulltext import retrieval
from revue_portee.i18n import DEFAULT_LOCALE, EXPORT_LANGUAGES, translations
from revue_portee.i18n import gettext as _
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.protocol import criteria, framing, notes, qualification, registration, suggestions
from revue_portee.protocol.ai_assist import AITaskError, CostPreview, default_provider_factory
from revue_portee.protocol.document import protocol_document
from revue_portee.reporting.document import render_docx, render_markdown
from revue_portee.reporting.flow import pending_items
from revue_portee.reporting.flow_svg import render_flow_svg
from revue_portee.reporting.formats import separator
from revue_portee.reporting.protocol import change_labels as report_change_labels
from revue_portee.reporting.protocol import checklist_status
from revue_portee.reporting.retained import write_csv, write_ris
from revue_portee.reporting.synthesis import frequency_table as synthesis_frequency
from revue_portee.reporting.synthesis import gaps as synthesis_gaps
from revue_portee.reporting.synthesis_export import MapContext, map_svg
from revue_portee.resources import (
    flow_template,
    grid_template,
    peters_checklist,
    tool_validation,
)
from revue_portee.screening import ai_screening, batch_ai, pilot, reassessment, studies
from revue_portee.screening import fulltext as fulltext_screening
from revue_portee.screening import main as main_screening
from revue_portee.screening import settings as screening_settings
from revue_portee.screening.archive import ArchiveKind, SecretInArchiveError, export_archive
from revue_portee.screening.methods import methods_document
from revue_portee.screening.report import flow_report, retained_references
from revue_portee.search import runs, strategies
from revue_portee.search import suggestions as term_suggestions
from revue_portee.search.runs import DescriptorSource, default_descriptor_source
from revue_portee.sources import (
    OpenAccessSources,
    SourceError,
    SourceFactory,
    default_source_factory,
)
from revue_portee.storage.project_folder import ProjectFolder, ProjectFolderError
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import projects
from revue_portee.storage.repositories import references as references_repo
from revue_portee.storage.repositories import screening as screening_repo
from revue_portee.synthesis import maps as synthesis_maps
from revue_portee.synthesis import narrative as synthesis_narrative
from revue_portee.version import tool_version as current_tool_version
from revue_portee.web import dedup_view, fulltext_view, grid_view, pilot_view, screening_view
from revue_portee.web.search_form import NEW_BLOCK, StrategyForm, read_strategy_form, rows_of

__all__ = ["ALLOWED_HOSTS", "create_app"]

ALLOWED_HOSTS = ("127.0.0.1", "localhost")
_PACKAGE = files("revue_portee.web")


@dataclass(frozen=True, slots=True)
class AppContext:
    folder: ProjectFolder
    now: Callable[[], datetime]
    tool_version: str
    csrf_token: str


class _LocalOnlyMiddleware(BaseHTTPMiddleware):
    """Refuse requests whose Host, or Origin for writes, is not this local server."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ALLOWED_HOSTS:
            return Response(_("Forbidden host."), status_code=400)
        origin = request.headers.get("origin")
        writes = request.method not in {"GET", "HEAD", "OPTIONS"}
        if (
            writes
            and origin
            and origin != "null"
            and urlsplit(origin).hostname not in ALLOWED_HOSTS
        ):
            return Response(_("Forbidden origin."), status_code=403)
        return await call_next(request)


def check_csrf(request: Request, csrf_token: Annotated[str, Form()] = "") -> None:
    """Every form posts the per-process token of the application that rendered it."""
    expected: str = request.app.state.csrf_token
    if not secrets.compare_digest(csrf_token, expected):
        raise HTTPException(status_code=403, detail=_("Invalid form token."))


Csrf = Annotated[None, Depends(check_csrf)]


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def pcc_labels() -> dict[str, str]:
    return {
        PccElement.POPULATION: _("Population"),
        PccElement.CONCEPT: _("Concept"),
        PccElement.CONTEXT: _("Context"),
        PccElement.OTHER: _("Cross-cutting (source type, language, period, design)"),
    }


def kind_labels() -> dict[str, str]:
    return {CriterionKind.INCLUSION: _("Inclusion"), CriterionKind.EXCLUSION: _("Exclusion")}


def status_labels() -> dict[str, str]:
    return {
        VersionStatus.DRAFT: _("draft"),
        VersionStatus.ACTIVE: _("in force"),
        VersionStatus.SUPERSEDED: _("superseded"),
    }


def field_labels() -> dict[str, str]:
    return {
        "pcc_element": _("PCC element"),
        "kind": _("Kind"),
        "text": _("Wording"),
        "guidance": _("Guidance"),
        "examples": _("Examples"),
        "counterexamples": _("Counterexamples"),
    }


def field_names(fields: Iterable[str]) -> str:
    labels = field_labels()
    return ", ".join(labels.get(field, field) for field in fields)


def suggestion_labels() -> dict[str, str]:
    return {
        SuggestionKind.REFORMULATION: _("Reformulation of the question"),
        SuggestionKind.SECONDARY_QUESTION: _("Secondary question"),
        SuggestionKind.POPULATION: _("Population"),
        SuggestionKind.CONCEPT: _("Concept"),
        SuggestionKind.CONTEXT: _("Context"),
    }


def outcome_labels() -> dict[str, str]:
    return {
        SuggestionOutcome.ACCEPTED: _("Accepted"),
        SuggestionOutcome.MODIFIED: _("Modified, then accepted"),
        SuggestionOutcome.REJECTED: _("Rejected"),
    }


def change_labels() -> dict[str, str]:
    return {change.value: label for change, label in report_change_labels(_).items()}


def section_labels() -> dict[str, str]:
    return {
        ProtocolSection.ABSTRACT: _("Abstract"),
        ProtocolSection.BACKGROUND: _("Background and rationale"),
        ProtocolSection.EXISTING_REVIEWS: _("Preliminary search for existing reviews"),
        ProtocolSection.OBJECTIVES: _("Objective"),
        ProtocolSection.SOURCES: _("Types of sources of evidence"),
        ProtocolSection.SEARCH: _("Search strategy"),
        ProtocolSection.INFORMATION_SOURCES: _("Information sources"),
        ProtocolSection.SELECTION: _(
            "Source of evidence selection (in addition to the generated text)"
        ),
        ProtocolSection.EXTRACTION: _("Data extraction"),
        ProtocolSection.ANALYSIS: _("Data analysis and presentation"),
        ProtocolSection.APPRAISAL: _("Critical appraisal"),
        ProtocolSection.CONSULTATION: _("Consultation"),
        ProtocolSection.ACKNOWLEDGEMENTS: _("Acknowledgements"),
        ProtocolSection.FUNDING: _("Funding"),
        ProtocolSection.CONFLICTS: _("Conflicts of interest"),
        ProtocolSection.REFERENCES: _("Additional references"),
    }


def role_labels() -> dict[str, str]:
    return {
        BlockRole.INCLUDE: _("Inclusion (combined with AND)"),
        BlockRole.EXCLUDE: _("Exclusion (removed with NOT)"),
    }


def language_labels() -> dict[str, str]:
    names = {
        "en": _("English"),
        "fr": _("French"),
        "es": _("Spanish"),
        "de": _("German"),
        "pt": _("Portuguese"),
        "it": _("Italian"),
    }
    return {code: names.get(code, code) for code in LANGUAGES}


def warning_labels() -> dict[str, str]:
    return {
        WarningKind.DESCRIPTOR_NOT_SUPPORTED: _("descriptor left out: vocabulary absent here"),
        WarningKind.FIELD_WIDENED: _("field not available: searched in title and abstract"),
        WarningKind.PUBLICATION_TYPE_NOT_SUPPORTED: _("publication type left out"),
        WarningKind.COMMA_REMOVED: _("comma removed (not allowed in OpenAlex filters)"),
        WarningKind.EMPTY_BLOCK: _("block without usable term: left out"),
        WarningKind.RAW_FILTER_IN_EXCLUSION: _(
            "OpenAlex filter of an exclusion block left out (a filter cannot be removed with NOT)"
        ),
        WarningKind.EXCLUSION_WITHOUT_INCLUSION: _(
            "exclusion blocks without inclusion block: no query (NOT needs records to remove from)"
        ),
        WarningKind.YEARS_IN_INTERFACE: _(
            "set the publication years with the limiter of the interface"
        ),
    }


def block_name(code: str) -> str:
    return _("limits (years, languages)") if code == LIMITS else code


def decimal_fr(value: Decimal | float, digits: int) -> str:
    """Number in French notation, e.g. « 0,90 »."""
    return f"{value:.{digits}f}".replace(".", ",")


def money(amount: Decimal, currency: str) -> str:
    """Amount in French notation, e.g. « 0,0123 USD »."""
    return decimal_fr(amount, 4) + " " + currency


# Errors of an AI request that are shown on the page (French messages).
_AI_ERRORS: tuple[type[Exception], ...] = (
    TaskNotAvailableError,
    UnknownPriceError,
    UnknownProviderError,
    UnsupportedParameterError,
    MissingSecretError,
    ProjectFolderError,
    suggestions.NoFramingError,
    qualification.NothingToQualifyError,
)


_TERM_ERRORS: tuple[type[Exception], ...] = (*_AI_ERRORS, term_suggestions.NoStrategyError)
_BATCH_ERRORS: tuple[type[Exception], ...] = (*_AI_ERRORS, batch_ai.NotBatchCapableError)
# Errors of a screening decision shown on the page.
_DECISION_ERRORS: tuple[type[Exception], ...] = (
    pilot.NotInRoundError,
    pilot.UnknownCriterionError,
    ValidationError,
)
_RECONCILE_ERRORS: tuple[type[Exception], ...] = (
    *_DECISION_ERRORS,
    main_screening.NotADisagreementError,
)
_VERIFY_ERRORS: tuple[type[Exception], ...] = (*_DECISION_ERRORS, reassessment.NotAChangeError)
_EXTRACTION_ERRORS: tuple[type[Exception], ...] = (*_AI_ERRORS, prefill.NoGridError)
_NARRATIVE_ERRORS: tuple[type[Exception], ...] = (
    *_EXTRACTION_ERRORS,
    synthesis_narrative.NothingToSynthesizeError,
    synthesis_narrative.UnknownFieldError,
)
_TEXT_DECISION_ERRORS: tuple[type[Exception], ...] = (
    *_DECISION_ERRORS,
    fulltext_screening.AIFirstError,
)
_TEXT_RECONCILE_ERRORS: tuple[type[Exception], ...] = (
    *_RECONCILE_ERRORS,
    fulltext_screening.NotBlindError,
)


# Archives written in exports/ (screening/archive.py), the only files served from there.
ARCHIVE_NAME = re.compile(r"archive-(publique|complete)-\d{8}T\d{6}Z\.zip")

# Key of the background job that compares the references (one at a time).
DEDUP_JOB = "dedoublonnage"
# Key of the background job where the AI examines pairs of reports (one at a time).
STUDY_JOB = "etudes-ia"
# Key of the background job where the AI pre-fills the extraction grid.
EXTRACTION_JOB = "extraction-ia"
# Key of the background job where the AI drafts the narrative synthesis of a field.
NARRATIVE_JOB = "narratif-ia-{code}"


def create_app(
    folder: ProjectFolder,
    *,
    now: Callable[[], datetime] = utc_now,
    tool_version: str | None = None,
    provider_factory: ProviderFactory = default_provider_factory,
    source_factory: SourceFactory = default_source_factory,
    descriptor_source: Callable[[], DescriptorSource] = default_descriptor_source,
    collector_factory: CollectorFactory | None = None,
    crossref_source: Callable[[], WorkSource] | None = None,
    open_access_finder: Callable[[], retrieval.OpenAccessFinder] = OpenAccessSources,
    jobs: BackgroundJobs | None = None,
    batch_wait: Callable[[float], None] = time.sleep,
    batch_poll_seconds: float = batch_ai.POLL_SECONDS,
) -> FastAPI:
    """Application serving one open project folder."""
    context = AppContext(
        folder=folder,
        now=now,
        tool_version=tool_version or current_tool_version(),
        csrf_token=secrets.token_urlsafe(32),
    )
    background = jobs or BackgroundJobs()
    collect_options: dict[str, Any] = (
        {} if collector_factory is None else {"factory": collector_factory}
    )
    crossref_options: dict[str, Any] = (
        {} if crossref_source is None else {"source": crossref_source}
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.csrf_token = context.csrf_token
    app.add_middleware(_LocalOnlyMiddleware)
    app.mount("/statique", StaticFiles(directory=str(_PACKAGE / "static")), name="static")

    templates = Jinja2Templates(directory=str(_PACKAGE / "templates"))
    templates.env.add_extension("jinja2.ext.i18n")
    templates.env.install_gettext_translations(translations(), newstyle=True)  # type: ignore[attr-defined]
    templates.env.globals.update(
        pcc_labels=pcc_labels,
        kind_labels=kind_labels,
        status_labels=status_labels,
        field_names=field_names,
        suggestion_labels=suggestion_labels,
        outcome_labels=outcome_labels,
        change_labels=change_labels,
        section_labels=section_labels,
        money=money,
        decimal_fr=decimal_fr,
        role_labels=role_labels,
        language_labels=language_labels,
        warning_labels=warning_labels,
        block_name=block_name,
        value_labels=pilot_view.value_labels,
        assessment_labels=pilot_view.assessment_labels,
        stopped_labels=pilot_view.stopped_labels,
        percent=pilot_view.percent,
        change_type_labels=screening_view.change_type_labels,
        Database=Database,
        NEW_BLOCK=NEW_BLOCK,
        modification_types=MODIFICATION_TYPES,
        PccElement=PccElement,
        ai_reviewer_in_evaluation=tool_validation().dataset_role == "development",
        CriterionKind=CriterionKind,
    )

    with folder.engine.connect() as connection:
        project = projects.get_project(connection)  # never changes once created

    def render(
        request: Request, name: str, values: Mapping[str, Any], *, status_code: int = 200
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            name,
            {"project": project, "csrf_token": context.csrf_token, "page": name} | dict(values),
            status_code=status_code,
        )

    def see_other(url: str) -> RedirectResponse:
        return RedirectResponse(url, status_code=303)

    # --- Framing ----------------------------------------------------------------------

    @app.get("/")
    def home() -> RedirectResponse:
        return see_other("/cadrage")

    def framing_page(
        request: Request,
        *,
        error: str | None = None,
        saved: bool = False,
        preview: CostPreview | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        return render(
            request,
            "cadrage.html",
            {
                "current": framing.current_framing(folder),
                "history": framing.framing_history(folder),
                "suggestions": suggestions.list_suggestions(folder),
                "preview": preview,
                "error": error,
                "saved": saved,
            },
            status_code=status_code,
        )

    @app.get("/cadrage", response_class=HTMLResponse)
    def show_framing(request: Request, enregistre: int = 0) -> HTMLResponse:
        return framing_page(request, saved=bool(enregistre))

    @app.post("/cadrage")
    def save_framing(
        request: Request,
        _csrf: Csrf,
        question: Annotated[str, Form()] = "",
        population: Annotated[str, Form()] = "",
        concept: Annotated[str, Form()] = "",
        contexte: Annotated[str, Form()] = "",
        questions_secondaires: Annotated[str, Form()] = "",
    ) -> Response:
        if not question.strip():
            return framing_page(request, error=_("The main question is required."), status_code=422)
        framing.save_framing(
            folder,
            Framing(
                question=question,
                population=population,
                concept=concept,
                context=contexte,
                secondary_questions=tuple(_lines(questions_secondaires)),
            ),
            now=now,
            tool_version=context.tool_version,
        )
        return see_other("/cadrage?enregistre=1")

    @app.post("/cadrage/suggestions/estimation")
    def estimate_suggestions(request: Request, _csrf: Csrf) -> Response:
        try:
            preview = suggestions.preview_suggestions(folder, factory=provider_factory)
        except _AI_ERRORS as error:
            return framing_page(request, error=str(error), status_code=422)
        return framing_page(request, preview=preview)

    @app.post("/cadrage/suggestions")
    def request_suggestions(request: Request, _csrf: Csrf) -> Response:
        try:
            suggestions.request_suggestions(
                folder, now=now, tool_version=context.tool_version, factory=provider_factory
            )
        except _AI_ERRORS as error:
            return framing_page(request, error=str(error), status_code=422)
        except AITaskError as error:
            return framing_page(request, error=str(error), status_code=502)
        return see_other("/cadrage#suggestions")

    @app.post("/cadrage/suggestions/{suggestion_id}")
    def review_suggestion(
        request: Request,
        suggestion_id: str,
        _csrf: Csrf,
        decision: Annotated[SuggestionOutcome, Form()],
        texte: Annotated[str, Form()] = "",
    ) -> Response:
        try:
            suggestions.review_suggestion(
                folder,
                suggestion_id,
                decision,
                text=texte,
                now=now,
                tool_version=context.tool_version,
            )
        except suggestions.UnknownSuggestionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (suggestions.AlreadyReviewedError, suggestions.MissingTextError) as error:
            return framing_page(request, error=str(error), status_code=422)
        return see_other(f"/cadrage#suggestion-{suggestion_id}")

    # --- Criteria ---------------------------------------------------------------------

    def criteria_page(
        request: Request,
        *,
        error: str | None = None,
        qualify_preview: CostPreview | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        state = criteria.criteria_state(folder)
        draft_diff = None
        if state.draft is not None and state.active is not None:
            draft_diff = diff_versions(state.active, state.draft)
        pending = qualification.pending_qualification(folder)
        return render(
            request,
            "criteres.html",
            {
                "state": state,
                "draft_diff": draft_diff,
                "proposals": {} if pending is None else pending.proposals,
                "qualify_preview": qualify_preview,
                "registration": registration.current_registration(folder),
                "error": error,
            },
            status_code=status_code,
        )

    @app.get("/criteres", response_class=HTMLResponse)
    def show_criteria(request: Request) -> HTMLResponse:
        return criteria_page(request)

    @app.post("/criteres/brouillon")
    def start_draft(_csrf: Csrf) -> RedirectResponse:
        criteria.start_draft(folder, now=now, tool_version=context.tool_version)
        return see_other("/criteres#brouillon")

    @app.post("/criteres/brouillon/ajouter")
    def add_criterion(
        request: Request,
        _csrf: Csrf,
        element: Annotated[PccElement, Form()],
        nature: Annotated[CriterionKind, Form()],
        texte: Annotated[str, Form()] = "",
        consignes: Annotated[str, Form()] = "",
        exemples: Annotated[str, Form()] = "",
        contre_exemples: Annotated[str, Form()] = "",
    ) -> Response:
        if not texte.strip():
            return criteria_page(
                request, error=_("The wording of the criterion is required."), status_code=422
            )
        added = criteria.add_criterion(
            folder,
            pcc_element=element,
            kind=nature,
            text=texte,
            guidance=consignes,
            examples=_lines(exemples),
            counterexamples=_lines(contre_exemples),
            now=now,
            tool_version=context.tool_version,
        )
        return see_other(f"/criteres#critere-{added.code}")

    @app.get("/criteres/brouillon/{code}", response_class=HTMLResponse)
    def edit_criterion_form(request: Request, code: str) -> HTMLResponse:
        state = criteria.criteria_state(folder)
        base = state.draft or state.active
        found = None if base is None else base.criterion(code)
        if found is None:
            raise HTTPException(
                status_code=404, detail=_("Unknown criterion: {code}.").format(code=code)
            )
        return render(
            request,
            "critere_modifier.html",
            {"criterion": found, "has_draft": state.draft is not None},
        )

    @app.post("/criteres/brouillon/{code}")
    def update_criterion(
        request: Request,
        code: str,
        _csrf: Csrf,
        nature: Annotated[CriterionKind, Form()],
        texte: Annotated[str, Form()] = "",
        consignes: Annotated[str, Form()] = "",
        exemples: Annotated[str, Form()] = "",
        contre_exemples: Annotated[str, Form()] = "",
    ) -> Response:
        if not texte.strip():
            return criteria_page(
                request, error=_("The wording of the criterion is required."), status_code=422
            )
        try:
            criteria.update_criterion(
                folder,
                code,
                kind=nature,
                text=texte,
                guidance=consignes,
                examples=_lines(exemples),
                counterexamples=_lines(contre_exemples),
                now=now,
                tool_version=context.tool_version,
            )
        except criteria.UnknownCriterionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return see_other(f"/criteres#critere-{code}")

    @app.post("/criteres/brouillon/{code}/retirer")
    def remove_criterion(code: str, _csrf: Csrf) -> RedirectResponse:
        try:
            criteria.remove_criterion(folder, code, now=now, tool_version=context.tool_version)
        except criteria.UnknownCriterionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return see_other("/criteres#brouillon")

    @app.post("/criteres/qualification/estimation")
    def estimate_qualification(request: Request, _csrf: Csrf) -> Response:
        try:
            preview = qualification.preview_proposals(folder, factory=provider_factory)
        except _AI_ERRORS as error:
            return criteria_page(request, error=str(error), status_code=422)
        return criteria_page(request, qualify_preview=preview)

    @app.post("/criteres/qualification")
    def request_qualification(request: Request, _csrf: Csrf) -> Response:
        try:
            qualification.request_proposals(
                folder, now=now, tool_version=context.tool_version, factory=provider_factory
            )
        except _AI_ERRORS as error:
            return criteria_page(request, error=str(error), status_code=422)
        except AITaskError as error:
            return criteria_page(request, error=str(error), status_code=502)
        return see_other("/criteres#qualification")

    @app.post("/criteres/activer")
    async def activate(
        request: Request, _csrf: Csrf, justification: Annotated[str, Form()] = ""
    ) -> Response:
        form = await request.form()
        choices: dict[str, ChangeType] = {}
        for key, value in form.multi_items():
            if key.startswith("qualification-") and isinstance(value, str):
                try:
                    choices[key.removeprefix("qualification-")] = ChangeType(value)
                except ValueError:
                    raise HTTPException(status_code=422, detail=_("Invalid form.")) from None
        try:
            activated = await run_in_threadpool(
                criteria.activate_draft,
                folder,
                rationale=justification,
                qualifications=choices,
                now=now,
                tool_version=context.tool_version,
            )
        except criteria.NoDraftError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except MissingRationaleError:
            return await run_in_threadpool(
                criteria_page,
                request,
                error=_("A rationale is required to create a new version of the criteria."),
                status_code=422,
            )
        except EmptyCriteriaError:
            return await run_in_threadpool(
                criteria_page,
                request,
                error=_("Add at least one criterion before activating."),
                status_code=422,
            )
        except qualification.MissingQualificationError as error:
            return await run_in_threadpool(
                criteria_page, request, error=str(error), status_code=422
            )
        return see_other(f"/criteres/versions/{activated.number}")

    @app.post("/criteres/abandonner")
    def discard(_csrf: Csrf) -> RedirectResponse:
        try:
            criteria.discard_draft(folder, now=now, tool_version=context.tool_version)
        except criteria.NoDraftError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return see_other("/criteres")

    @app.get("/criteres/versions/{number}", response_class=HTMLResponse)
    def show_version(request: Request, number: int) -> HTMLResponse:
        try:
            found = criteria.version(folder, number)
        except criteria.UnknownVersionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if found.status is VersionStatus.DRAFT:
            return see_other("/criteres#brouillon")  # type: ignore[return-value]
        return render(
            request,
            "version.html",
            {"version": found, "changes": qualification.version_changes(folder, found.id)},
        )

    @app.get("/criteres/differentiel", response_class=HTMLResponse)
    def show_diff(request: Request, de: int, a: int) -> HTMLResponse:
        try:
            delta = criteria.diff(folder, de, a)
        except criteria.UnknownVersionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return render(
            request,
            "differentiel.html",
            {"diff": delta, "versions": criteria.criteria_state(folder).versions},
        )

    # --- Search -----------------------------------------------------------------------

    def search_page(
        request: Request,
        *,
        error: str | None = None,
        saved: bool = False,
        form: StrategyForm | None = None,
        key_lines: str | None = None,
        preview: CostPreview | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        current = strategies.current_strategy(folder)
        strategy = None if current is None else current.strategy
        if form is None:
            limits = None if strategy is None else strategy.limits
            form = StrategyForm(
                rows=rows_of(strategy),
                year_from=str(limits.year_from or "") if limits else "",
                year_to=str(limits.year_to or "") if limits else "",
                languages=limits.languages if limits else (),
            )
        key_articles = runs.current_key_articles(folder)
        if key_lines is None:
            key_lines = (
                "" if key_articles is None else "\n".join(a.value for a in key_articles.articles)
            )
        checks = runs.sensitivity_checks(folder)
        latest_checks = {}
        queries = strategies.current_queries(folder)
        query_databases = {q.id: q.database for q in queries.values()}
        for run, check in checks:
            if run.query_id in query_databases:
                latest_checks[query_databases[run.query_id]] = (run, check)
        return render(
            request,
            "recherche.html",
            {
                "current": current,
                "form": form,
                "errors": form.errors,
                "queries": queries,
                "counts": runs.latest_runs(folder),
                "history": strategies.strategy_history(folder),
                "headings": runs.headings_to_check(folder),
                "descriptor_checks": runs.descriptor_checks(folder),
                "key_articles": key_articles,
                "key_lines": key_lines,
                "sensitivity": latest_checks,
                "suggestions": term_suggestions.list_term_suggestions(folder),
                "preview": preview,
                "error": error,
                "saved": saved,
            },
            status_code=status_code,
        )

    def _database(value: str) -> Database:
        try:
            database = Database(value)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=_("Unknown database.")) from error
        if database is Database.PSYCINFO_EBSCO:
            raise HTTPException(status_code=404, detail=_("Unknown database."))
        return database

    @app.get("/recherche", response_class=HTMLResponse)
    def show_search(request: Request, enregistre: int = 0) -> HTMLResponse:
        return search_page(request, saved=bool(enregistre))

    @app.post("/recherche/strategie")
    async def save_search_strategy(request: Request, _csrf: Csrf) -> Response:
        raw = await request.form()
        values = {key: value for key, value in raw.items() if isinstance(value, str)}
        languages = [value for value in raw.getlist("langues") if isinstance(value, str)]
        used = await run_in_threadpool(strategies.used_block_codes, folder)
        form = read_strategy_form(values, languages, used_codes=used)
        if form.strategy is None:
            return search_page(request, form=form, status_code=422)
        try:
            await run_in_threadpool(
                strategies.save_strategy,
                folder,
                form.strategy,
                rationale=form.rationale,
                now=now,
                tool_version=context.tool_version,
            )
        except strategies.EmptyStrategyError as error:
            return search_page(request, error=str(error), form=form, status_code=422)
        return see_other("/recherche?enregistre=1")

    @app.post("/recherche/comptes/{database}")
    def count_search_results(request: Request, database: str, _csrf: Csrf) -> Response:
        chosen = _database(database)
        try:
            runs.count_results(
                folder, chosen, now=now, tool_version=context.tool_version, factory=source_factory
            )
        except (runs.NoQueryError, MissingSecretError) as error:
            return search_page(request, error=str(error), status_code=422)
        except SourceError as error:
            return search_page(request, error=str(error), status_code=502)
        return see_other(f"/recherche#requete-{chosen.value}")

    @app.post("/recherche/descripteurs")
    def check_search_descriptors(request: Request, _csrf: Csrf) -> Response:
        try:
            runs.check_descriptors(
                folder, now=now, tool_version=context.tool_version, source=descriptor_source
            )
        except MissingSecretError as error:
            return search_page(request, error=str(error), status_code=422)
        except SourceError as error:
            return search_page(request, error=str(error), status_code=502)
        return see_other("/recherche#descripteurs")

    @app.post("/recherche/articles-cles")
    def save_search_key_articles(
        request: Request, _csrf: Csrf, articles: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            runs.save_key_articles(
                folder, articles.splitlines(), now=now, tool_version=context.tool_version
            )
        except runs.InvalidKeyArticlesError as error:
            return search_page(request, error=str(error), key_lines=articles, status_code=422)
        return see_other("/recherche#articles-cles")

    @app.post("/recherche/sensibilite/{database}")
    def check_search_sensitivity(request: Request, database: str, _csrf: Csrf) -> Response:
        chosen = _database(database)
        try:
            runs.check_sensitivity(
                folder, chosen, now=now, tool_version=context.tool_version, factory=source_factory
            )
        except (runs.NoQueryError, runs.NoKeyArticlesError, MissingSecretError) as error:
            return search_page(request, error=str(error), status_code=422)
        except SourceError as error:
            return search_page(request, error=str(error), status_code=502)
        return see_other(f"/recherche#sensibilite-{chosen.value}")

    @app.post("/recherche/suggestions/estimation")
    def estimate_term_suggestions(request: Request, _csrf: Csrf) -> Response:
        try:
            preview = term_suggestions.preview_term_suggestions(folder, factory=provider_factory)
        except _TERM_ERRORS as error:
            return search_page(request, error=str(error), status_code=422)
        return search_page(request, preview=preview)

    @app.post("/recherche/suggestions")
    def request_term_suggestions(request: Request, _csrf: Csrf) -> Response:
        try:
            term_suggestions.request_term_suggestions(
                folder, now=now, tool_version=context.tool_version, factory=provider_factory
            )
        except _TERM_ERRORS as error:
            return search_page(request, error=str(error), status_code=422)
        except AITaskError as error:
            return search_page(request, error=str(error), status_code=502)
        return see_other("/recherche#suggestions")

    @app.post("/recherche/suggestions/{suggestion_id}")
    def review_term_suggestion(
        request: Request,
        suggestion_id: str,
        _csrf: Csrf,
        decision: Annotated[SuggestionOutcome, Form()],
        terme: Annotated[str, Form()] = "",
    ) -> Response:
        try:
            term_suggestions.review_term_suggestion(
                folder,
                suggestion_id,
                decision,
                line=terme,
                now=now,
                tool_version=context.tool_version,
            )
        except term_suggestions.UnknownSuggestionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (
            term_suggestions.AlreadyReviewedError,
            term_suggestions.BlockGoneError,
            term_suggestions.InvalidTermError,
        ) as error:
            return search_page(request, error=str(error), status_code=422)
        return see_other(f"/recherche#suggestion-{suggestion_id}")

    # --- Collection -------------------------------------------------------------------

    def collection_context() -> dict[str, Any]:
        states = list(collection.collection_states(folder).values())
        with folder.engine.connect() as connection:
            counts = references_repo.count_by_source(connection)
            total = references_repo.count_references(connection)
            candidates = references_repo.count_enrichment_candidates(connection)
        return {
            "states": list(reversed(states)),
            "running": {s.run.id for s in states if background.running(s.run.id)},
            "job_errors": {
                s.run.id: error for s in states if (error := background.error(s.run.id))
            },
            "queries": strategies.current_queries(folder),
            "counts": counts,
            "total": total,
            "imports": list(reversed(imports.imported_files(folder))),
            "candidates": candidates,
            "crossref_running": background.running("crossref"),
            "crossref_error": background.error("crossref"),
            "declared_databases": imports.DECLARED_DATABASES,
        }

    def collection_page(
        request: Request,
        *,
        error: str | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        return render(
            request,
            "collecte.html",
            collection_context() | {"error": error, "message": message},
            status_code=status_code,
        )

    def _run_job(run_id: str) -> None:
        collection.collect(
            folder, run_id, now=now, tool_version=context.tool_version, **collect_options
        )

    @app.get("/collecte", response_class=HTMLResponse)
    def show_collection(request: Request, importe: int = 0) -> HTMLResponse:
        return collection_page(request, message=_("File imported.") if importe else None)

    @app.get("/collecte/etat", response_class=HTMLResponse)
    def collection_progress(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "_collecte_etat.html",
            {"csrf_token": context.csrf_token} | collection_context(),
        )

    @app.post("/collecte/lancer/{database}")
    def start_collection(request: Request, database: str, _csrf: Csrf) -> Response:
        try:
            chosen = Database(database)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=_("Unknown database.")) from error
        try:
            run = collection.start_collection(
                folder, chosen, now=now, tool_version=context.tool_version
            )
        except (collection.NoCollectableQueryError, collection.CollectionOpenError) as error:
            return collection_page(request, error=str(error), status_code=422)
        background.start(run.id, lambda: _run_job(run.id))
        return see_other("/collecte#collectes")

    @app.post("/collecte/reprendre/{run_id}")
    def resume_collection(request: Request, run_id: str, _csrf: Csrf) -> Response:
        state = collection.collection_states(folder).get(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail=_("Unknown collection."))
        if state.finished:
            return collection_page(
                request, error=str(collection.AlreadyEndedError()), status_code=422
            )
        background.start(run_id, lambda: _run_job(run_id))
        return see_other("/collecte#collectes")

    @app.post("/collecte/import")
    async def import_file(request: Request, _csrf: Csrf) -> Response:
        form = await request.form()
        upload = form.get("fichier")
        declared = form.get("base", "")
        if upload is None or isinstance(upload, str) or not upload.filename:
            return collection_page(request, error=_("Choose a RIS file."), status_code=422)
        content = await upload.read()
        try:
            await run_in_threadpool(
                imports.import_ris,
                folder,
                upload.filename,
                content,
                database=declared if isinstance(declared, str) else "",
                now=now,
                tool_version=context.tool_version,
            )
        except (
            imports.AlreadyImportedError,
            imports.NothingToImportError,
            imports.UnreadableFileError,
        ) as error:
            return collection_page(request, error=str(error), status_code=422)
        return see_other("/collecte?importe=1#imports")

    @app.post("/collecte/crossref")
    def enrich_with_crossref(_csrf: Csrf) -> Response:
        background.start(
            "crossref",
            lambda: enrichment.enrich_references(
                folder, now=now, tool_version=context.tool_version, **crossref_options
            ),
        )
        return see_other("/collecte#crossref")

    # --- Duplicates -------------------------------------------------------------------

    def dedup_page(
        request: Request,
        *,
        page: int = 1,
        error: str | None = None,
        message: str | None = None,
        settings: DedupSettings | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        state = deduplication.dedup_state(folder)
        shown, pages, page_number = dedup_view.page_of(state.groups, page)
        kept_apart = [d for d in state.decisions.values() if d.outcome is PairOutcome.NOT_DUPLICATE]
        return render(
            request,
            "doublons.html",
            {
                "run": state.run,
                "counts": state.counts,
                "new_references": state.new_references,
                "settings": settings or dedup_view.default_settings(state),
                "pending": state.pending,
                "pairs_shown": dedup_view.PAIRS_SHOWN,
                "references": state.references,
                "sources": state.sources,
                "groups": shown,
                "group_count": len(state.groups),
                "pages": pages,
                "page_number": page_number,
                "kept_apart": sorted(kept_apart, key=lambda d: d.created_at, reverse=True),
                "rule_labels": dedup_view.rule_labels,
                "reason_labels": dedup_view.reason_labels,
                "pair_rows": dedup_view.pair_rows,
                "group_links": dedup_view.links_by_group(shown, state),
                "error": error,
                "message": message,
            }
            | dedup_job_context(),
            status_code=status_code,
        )

    def dedup_job_context() -> dict[str, Any]:
        return {
            "dedup_running": background.running(DEDUP_JOB),
            "dedup_error": background.error(DEDUP_JOB),
        }

    @app.get("/doublons", response_class=HTMLResponse)
    def show_duplicates(request: Request, page: int = 1) -> HTMLResponse:
        return dedup_page(request, page=page)

    @app.get("/doublons/etat", response_class=HTMLResponse)
    def dedup_progress(request: Request) -> HTMLResponse:
        values = dedup_job_context()
        response = templates.TemplateResponse(request, "_doublons_etat.html", values)
        if not values["dedup_running"]:
            response.headers["HX-Refresh"] = "true"  # show the results of the run
        return response

    @app.post("/doublons/lancer")
    def run_deduplication(
        request: Request,
        _csrf: Csrf,
        review_from: Annotated[str, Form()] = "",
        auto_from: Annotated[str, Form()] = "",
    ) -> Response:
        defaults = DedupSettings()
        try:
            settings = DedupSettings(
                review_from=dedup_view.parse_threshold(review_from, defaults.review_from),
                auto_from=dedup_view.parse_threshold(auto_from, defaults.auto_from),
            )
        except ValueError:
            return dedup_page(
                request,
                error=_(
                    "Thresholds must be numbers from 0 to 1, the first one not above the second."
                ),
                status_code=422,
            )
        with folder.engine.connect() as connection:
            if references_repo.count_references(connection) == 0:
                error = str(deduplication.NoReferencesError())
                return dedup_page(request, error=error, settings=settings, status_code=422)
        started = background.start(
            DEDUP_JOB,
            lambda: deduplication.run_deduplication(
                folder, settings, now=now, tool_version=context.tool_version
            ),
        )
        if not started:
            return dedup_page(
                request,
                error=_("A deduplication is already running."),
                settings=settings,
                status_code=422,
            )
        return see_other("/doublons#lancer")

    @app.post("/doublons/paire")
    def decide_duplicate_pair(
        request: Request,
        _csrf: Csrf,
        reference_a: Annotated[str, Form()] = "",
        reference_b: Annotated[str, Form()] = "",
        outcome: Annotated[str, Form()] = "",
        retour: Annotated[str, Form()] = "paires",
    ) -> Response:
        try:
            chosen = PairOutcome(outcome)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=_("Unknown decision.")) from error
        try:
            deduplication.decide_pair(
                folder, reference_a, reference_b, chosen, now=now, tool_version=context.tool_version
            )
        except deduplication.UnknownPairError as error:
            return dedup_page(request, error=str(error), status_code=422)
        anchor = retour if retour in ("paires", "groupes", "separees") else "paires"
        return see_other(f"/doublons#{anchor}")

    # --- Pilot ------------------------------------------------------------------------

    # Result of the last AI batch of each round, shown on the round page.
    last_batches: dict[str, ai_screening.AIBatchResult] = {}

    def pilot_job(round_id: str) -> str:
        return f"pilote-{round_id}"

    def pilot_home(
        request: Request,
        *,
        error: str | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        with folder.engine.connect() as connection:
            budget = screening_repo.latest_budget(connection)
            spent = screening_repo.total_spent(connection)
            active = criteria_repo.get_active_version(connection)
        return render(
            request,
            "pilote.html",
            {
                "budget": budget,
                "spent": spent,
                "active": active,
                "default_size": folder.ai_settings().supervision.pilot_sample_size,
                "rounds": pilot.list_rounds(folder),
                "error": error,
                "message": message,
            },
            status_code=status_code,
        )

    def pilot_job_context(round_id: str) -> dict[str, Any]:
        job = pilot_job(round_id)
        return {
            "round_id": round_id,
            "running": background.running(job),
            "job_error": background.error(job),
            "last_batch": last_batches.get(round_id),
        }

    def round_page(
        request: Request,
        round_id: str,
        *,
        error: str | None = None,
        message: str | None = None,
        preview: CostPreview | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        try:
            state = pilot.pilot_state(folder, round_id)
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        return render(
            request,
            "pilote_tour.html",
            {
                "state": state,
                "preview": preview,
                "ceiling": pilot_view.batch_ceiling(preview.estimate) if preview else None,
                "target": folder.ai_settings().supervision.target_sensitivity,
                "error": error,
                "message": message,
            }
            | pilot_job_context(round_id),
            status_code=status_code,
        )

    @app.get("/pilote", response_class=HTMLResponse)
    def show_pilot(request: Request, budget: int = 0) -> HTMLResponse:
        return pilot_home(request, message=_("Budget saved.") if budget else None)

    @app.post("/pilote/budget")
    def save_budget(
        request: Request, _csrf: Csrf, montant: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            amount = pilot_view.parse_amount(montant)
        except ValueError:
            return pilot_home(
                request, error=_("The ceiling must be a positive amount."), status_code=422
            )
        screening_settings.set_budget(folder, amount, now=now, tool_version=context.tool_version)
        return see_other("/pilote?budget=1#budget")

    @app.post("/pilote/lancer")
    def draw_pilot(
        request: Request,
        _csrf: Csrf,
        taille: Annotated[str, Form()] = "",
        graine: Annotated[str, Form()] = "",
    ) -> Response:
        try:
            size = int(taille) if taille.strip() else None
            seed = int(graine) if graine.strip() else None
        except ValueError:
            size = seed = -1
        if (size is not None and size < 1) or (seed is not None and seed < 0):
            return pilot_home(
                request,
                error=_("The size must be a positive whole number, the seed a whole number."),
                status_code=422,
            )
        try:
            drawn = pilot.start_pilot(
                folder, size=size, seed=seed, now=now, tool_version=context.tool_version
            )
        except (pilot.NoActiveCriteriaError, pilot.NoReferencesError) as error:
            return pilot_home(request, error=str(error), status_code=422)
        return see_other(f"/pilote/{drawn.id}")

    @app.get("/pilote/{round_id}", response_class=HTMLResponse)
    def show_round(request: Request, round_id: str, decide: int = 0) -> HTMLResponse:
        message = None
        if decide == 1:
            message = _("Decision recorded.")
        elif decide == 2:
            message = _("Calibration fitted.")
        elif decide == 3:
            message = _("Thresholds fixed.")
        return round_page(request, round_id, message=message)

    @app.get("/pilote/{round_id}/etat", response_class=HTMLResponse)
    def round_progress(request: Request, round_id: str) -> HTMLResponse:
        values = pilot_job_context(round_id)
        response = templates.TemplateResponse(
            request, "_pilote_etat.html", {"csrf_token": context.csrf_token} | values
        )
        if not values["running"]:
            response.headers["HX-Refresh"] = "true"  # show the decisions of the batch
        return response

    @app.post("/pilote/{round_id}/decision")
    async def decide_reference(request: Request, round_id: str, _csrf: Csrf) -> Response:
        form = await request.form()
        reference = str(form.get("reference", ""))
        cited = [str(code) for code in form.getlist("criteres")]
        try:
            value = DecisionValue(str(form.get("valeur", "")))
        except ValueError:
            return round_page(request, round_id, error=_("Choose a decision."), status_code=422)
        try:
            await run_in_threadpool(
                pilot.record_human_decision,
                folder,
                round_id,
                reference,
                value,
                criteria_cited=cited,
                rationale=str(form.get("justification", "")).strip(),
                now=now,
                tool_version=context.tool_version,
            )
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        except (pilot.NotInRoundError, pilot.UnknownCriterionError, ValidationError) as error:
            message = (
                _("Cite at least one criterion to exclude a reference.")
                if isinstance(error, ValidationError)
                else str(error)
            )
            return round_page(request, round_id, error=message, status_code=422)
        return see_other(f"/pilote/{round_id}?decide=1#tri")

    @app.post("/pilote/{round_id}/ia/estimation")
    def estimate_ai(request: Request, round_id: str, _csrf: Csrf) -> Response:
        try:
            preview = ai_screening.preview_ai(folder, round_id, factory=provider_factory)
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        except _AI_ERRORS as error:
            return round_page(request, round_id, error=str(error), status_code=422)
        return round_page(request, round_id, preview=preview)

    @app.post("/pilote/{round_id}/ia")
    def screen_with_ai(
        request: Request, round_id: str, _csrf: Csrf, plafond: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            pilot.get_round(folder, round_id)
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        try:
            limit = pilot_view.parse_amount(plafond)
        except ValueError:
            return round_page(
                request,
                round_id,
                error=_("The ceiling must be a positive amount."),
                status_code=422,
            )
        with folder.engine.connect() as connection:
            if screening_repo.latest_budget(connection) is None:
                error = str(screening_settings.BudgetNotSetError())
                return round_page(request, round_id, error=error, status_code=422)

        def work() -> None:
            last_batches[round_id] = ai_screening.run_ai(
                folder,
                round_id,
                batch_limit=limit,
                factory=provider_factory,
                now=now,
                tool_version=context.tool_version,
            )

        if not background.start(pilot_job(round_id), work):
            return round_page(
                request,
                round_id,
                error=_("An AI batch is already running on this round."),
                status_code=422,
            )
        return see_other(f"/pilote/{round_id}#ia")

    @app.post("/pilote/{round_id}/etalonnage")
    def calibrate(request: Request, round_id: str, _csrf: Csrf) -> Response:
        try:
            pilot.fit_round_calibration(
                folder, round_id, now=now, tool_version=context.tool_version
            )
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        except pilot.NothingToCalibrateError as error:
            return round_page(request, round_id, error=str(error), status_code=422)
        return see_other(f"/pilote/{round_id}?decide=2#etalonnage")

    @app.post("/pilote/{round_id}/seuils")
    def fix_thresholds(
        request: Request,
        round_id: str,
        _csrf: Csrf,
        exclure: Annotated[str, Form()] = "",
        inclure: Annotated[str, Form()] = "",
        cible: Annotated[str, Form()] = "",
        motif: Annotated[str, Form()] = "",
        etalonne: Annotated[str, Form()] = "",
    ) -> Response:
        try:
            state = pilot.pilot_state(folder, round_id)
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        try:
            low = pilot_view.parse_probability(exclure)
            high = pilot_view.parse_probability(inclure)
            target = pilot_view.parse_probability(cible)
            thresholds = Thresholds(exclude_below=low, include_above=high)
        except (ValueError, ValidationError):
            return round_page(
                request,
                round_id,
                error=_(
                    "Thresholds must be numbers from 0 to 1, the first one not above the second."
                ),
                status_code=422,
            )
        if not motif.strip():
            return round_page(
                request,
                round_id,
                error=_("Give the justification of the thresholds."),
                status_code=422,
            )
        if target <= 0:
            return round_page(
                request,
                round_id,
                error=_("The target sensitivity must be above 0."),
                status_code=422,
            )
        calibration = state.calibration if etalonne and state.calibration else None
        screening_settings.set_thresholds(
            folder,
            thresholds,
            justification=motif.strip(),
            target_sensitivity=Decimal(str(target)),
            round_id=round_id,
            calibration_id=calibration.id if calibration else None,
            now=now,
            tool_version=context.tool_version,
        )
        return see_other(f"/pilote/{round_id}?decide=3#etalonnage")

    # --- Main screening, reconciliation, reassessment ----------------------------------

    def batch_job(round_id: str) -> str:
        return f"lots-{round_id}"

    def ai_context(round_id: str) -> dict[str, Any]:
        job = batch_job(round_id)
        return {
            "round_id": round_id,
            "waiting": len(batch_ai.waiting_for_ai(folder, round_id)),
            "pending": batch_ai.pending_batches(folder, round_id),
            "running": background.running(job),
            "error": background.error(job),
        }

    def require_main() -> ScreeningRound:
        found = main_screening.main_round(folder)
        if found is None:
            raise HTTPException(status_code=404, detail=_("The screening has not started."))
        return found

    def round_page_url(round_id: str) -> str:
        """Page of a round: the screening, or the reassessment of an impact."""
        for screening, home in (
            (main_screening.main_round(folder), "/tri"),
            (fulltext_screening.main_round(folder), "/textes/tri"),
        ):
            if screening is None:
                continue
            if screening.id == round_id:
                return home
            for impact in reassessment.impacts(folder, screening.id):
                if impact.reassessment_round_id == round_id:
                    return f"/tri/reevaluation/{impact.id}"
        raise HTTPException(status_code=404, detail=_("Unknown round."))

    def version_numbers() -> dict[str, int]:
        with folder.engine.connect() as connection:
            return {v.id: v.number for v in criteria_repo.list_versions(connection)}

    def screening_home(
        request: Request,
        *,
        error: str | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        screening = main_screening.main_round(folder)
        with folder.engine.connect() as connection:
            active = criteria_repo.get_active_version(connection)
        values: dict[str, Any] = {"main": screening, "active": active}
        if screening is not None:
            state = main_screening.main_state(folder, screening.id)
            values |= {
                "counts": main_screening.progress(state),
                "ai_main": ai_context(screening.id),
                "to_assess": reassessment.next_version_to_assess(folder, screening.id),
                "impacts": reassessment.impacts(folder, screening.id),
                "versions": version_numbers(),
            }
        return render(
            request,
            "tri.html",
            values | {"error": error, "message": message},
            status_code=status_code,
        )

    @app.get("/tri", response_class=HTMLResponse)
    def show_screening(request: Request, ok: str = "") -> HTMLResponse:
        messages = {
            "ajout": _("New references added."),
            "lot": _("AI screening started."),
            "suivi": _("Following the running batches."),
        }
        return screening_home(request, message=messages.get(ok))

    @app.post("/tri/lancer")
    def start_screening(
        request: Request, _csrf: Csrf, graine: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            seed = int(graine) if graine.strip() else None
        except ValueError:
            seed = -1
        if seed is not None and seed < 0:
            return screening_home(
                request, error=_("The seed must be a whole number."), status_code=422
            )
        try:
            main_screening.start_main(folder, seed=seed, now=now, tool_version=context.tool_version)
        except (
            pilot.NoActiveCriteriaError,
            pilot.NoReferencesError,
            main_screening.MainRoundExistsError,
        ) as error:
            return screening_home(request, error=str(error), status_code=422)
        return see_other("/tri")

    @app.post("/tri/ajouter")
    def add_references(_csrf: Csrf) -> Response:
        screening = require_main()
        main_screening.add_new_references(
            folder, screening.id, now=now, tool_version=context.tool_version
        )
        return see_other("/tri?ok=ajout")

    def reference_page(
        request: Request,
        *,
        priority: bool,
        skipped: list[str],
        error: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        screening = require_main()
        reference_id = main_screening.next_reference(
            folder, screening.id, priority=priority, skip=skipped
        )
        with folder.engine.connect() as connection:
            total = screening_repo.member_count(connection, screening.id)
            done = screening_repo.count_decided(
                connection,
                screening.id,
                decided_in=main_screening.decided_in(connection, screening),
            )
            criteria_version = criteria_repo.get_active_version(connection)
        found = None if reference_id is None else enriched_reference(folder, reference_id)
        return render(
            request,
            "tri_reference.html",
            {
                "ref": found,
                "criteria": criteria_version,
                "priority": priority,
                "skipped": skipped,
                "done": done,
                "total": total,
                "values": pilot_view.value_labels(),
                "error": error,
            },
            status_code=status_code,
        )

    @app.get("/tri/trier", response_class=HTMLResponse)
    def screen_next(request: Request, priorite: int = 0, passer: str = "") -> HTMLResponse:
        return reference_page(
            request, priority=bool(priorite), skipped=screening_view.skip_list(passer)
        )

    def decision_form(
        form: Any,  # noqa: ANN401 - Starlette form data
    ) -> tuple[str, DecisionValue | None, list[str], str]:
        try:
            value: DecisionValue | None = DecisionValue(str(form.get("valeur", "")))
        except ValueError:
            value = None
        return (
            str(form.get("reference", "")),
            value,
            [str(code) for code in form.getlist("criteres")],
            str(form.get("justification", "")),
        )

    def decision_error(error: Exception) -> str:
        if isinstance(error, ValidationError):
            return _("Cite at least one criterion to exclude a reference.")
        return str(error)

    @app.post("/tri/decision")
    async def decide(request: Request, _csrf: Csrf, priorite: int = 0) -> Response:
        screening = require_main()
        reference_id, value, cited, note = decision_form(await request.form())
        priority = bool(priorite)
        if value is None:
            return reference_page(
                request,
                priority=priority,
                skipped=[],
                error=_("Choose a decision."),
                status_code=422,
            )
        try:
            await run_in_threadpool(
                main_screening.record_decision,
                folder,
                screening.id,
                reference_id,
                value,
                criteria_cited=cited,
                rationale=note,
                now=now,
                tool_version=context.tool_version,
            )
        except _DECISION_ERRORS as error:
            return reference_page(
                request,
                priority=priority,
                skipped=[],
                error=decision_error(error),
                status_code=422,
            )
        return see_other("/tri/trier?priorite=1" if priority else "/tri/trier")

    def reconciliation_page(
        request: Request,
        *,
        error: str | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        screening = require_main()
        state = main_screening.main_state(folder, screening.id)
        reference_id = state.queue[0] if state.queue else None
        with folder.engine.connect() as connection:
            criteria_version = criteria_repo.get_active_version(connection)
        values: dict[str, Any] = {
            "ref": None,
            "left": len(state.queue),
            "criteria": criteria_version,
            "values": pilot_view.value_labels(),
            "error": error,
            "message": message,
        }
        if reference_id is not None:
            values |= {
                "ref": enriched_reference(folder, reference_id),
                "human": state.human[reference_id],
                "a": state.visible_ai(reference_id),
            }
        return render(request, "tri_reconciliation.html", values, status_code=status_code)

    @app.get("/tri/reconciliation", response_class=HTMLResponse)
    def show_reconciliation(request: Request, ok: int = 0) -> HTMLResponse:
        return reconciliation_page(request, message=_("Final decision recorded.") if ok else None)

    @app.post("/tri/reconciliation")
    async def reconcile_reference(request: Request, _csrf: Csrf) -> Response:
        screening = require_main()
        reference_id, value, cited, note = decision_form(await request.form())
        if value is None:
            return reconciliation_page(request, error=_("Choose a decision."), status_code=422)
        try:
            await run_in_threadpool(
                main_screening.reconcile,
                folder,
                screening.id,
                reference_id,
                value,
                criteria_cited=cited,
                rationale=note,
                now=now,
                tool_version=context.tool_version,
            )
        except _RECONCILE_ERRORS as error:
            return reconciliation_page(request, error=decision_error(error), status_code=422)
        return see_other("/tri/reconciliation?ok=1")

    # AI batches of a round (main screening or reassessment).

    def run_batches(round_id: str, limit: Decimal | None) -> None:
        if limit is not None:
            batch_ai.submit(
                folder,
                round_id,
                batch_limit=limit,
                factory=provider_factory,
                now=now,
                tool_version=context.tool_version,
            )
        batch_ai.follow(
            folder,
            round_id,
            factory=provider_factory,
            now=now,
            tool_version=context.tool_version,
            wait=batch_wait,
            poll_seconds=batch_poll_seconds,
        )

    @app.post("/tri/ia/{round_id}/estimation")
    def estimate_batches(request: Request, round_id: str, _csrf: Csrf) -> Response:
        back = round_page_url(round_id)
        try:
            preview = batch_ai.preview(folder, round_id, factory=provider_factory)
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        except _BATCH_ERRORS as error:
            return screening_home(request, error=str(error), status_code=422)
        return render(
            request,
            "tri_ia.html",
            {
                "preview": preview,
                "ceiling": pilot_view.batch_ceiling(preview.estimate),
                "round_id": round_id,
                "back": back,
            },
        )

    @app.post("/tri/ia/{round_id}/lancer")
    def start_batches(
        request: Request, round_id: str, _csrf: Csrf, plafond: Annotated[str, Form()] = ""
    ) -> Response:
        back = round_page_url(round_id)
        try:
            limit = pilot_view.parse_amount(plafond)
        except ValueError:
            return screening_home(
                request, error=_("The ceiling must be a positive amount."), status_code=422
            )
        with folder.engine.connect() as connection:
            if screening_repo.latest_budget(connection) is None:
                error = str(screening_settings.BudgetNotSetError())
                return screening_home(request, error=error, status_code=422)
        if not background.start(batch_job(round_id), lambda: run_batches(round_id, limit)):
            return screening_home(
                request, error=_("AI batches are already followed for this round."), status_code=422
            )
        return see_other(back + ("&" if "?" in back else "?") + "ok=lot")

    @app.post("/tri/ia/{round_id}/suivre")
    def follow_batches(round_id: str, _csrf: Csrf) -> Response:
        back = round_page_url(round_id)
        background.start(batch_job(round_id), lambda: run_batches(round_id, None))
        return see_other(back + ("&" if "?" in back else "?") + "ok=suivi")

    @app.get("/tri/ia/{round_id}/etat", response_class=HTMLResponse)
    def batches_progress(request: Request, round_id: str) -> HTMLResponse:
        round_page_url(round_id)  # 404 for an unknown round
        ai = ai_context(round_id)
        response = templates.TemplateResponse(
            request, "_tri_ia_etat.html", {"ai": ai, "csrf_token": context.csrf_token}
        )
        if not ai["running"]:
            response.headers["HX-Refresh"] = "true"  # show the decisions of the batches
        return response

    # Impact of a criteria change and reassessment.

    @app.post("/tri/impact")
    def assess_impact(
        request: Request, _csrf: Csrf, toutes: Annotated[str, Form()] = ""
    ) -> Response:
        screening = require_main()
        try:
            impact = reassessment.assess(
                folder,
                screening.id,
                sample_clarifications=not toutes,
                now=now,
                tool_version=context.tool_version,
            )
        except reassessment.NothingToAssessError as error:
            return screening_home(request, error=str(error), status_code=422)
        if impact.reassessment_round_id is None:
            return see_other("/tri")
        return see_other(f"/tri/reevaluation/{impact.id}")

    def reassessment_page(
        request: Request,
        impact_id: str,
        *,
        error: str | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        try:
            state = reassessment.reassessment_state(folder, impact_id)
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        reference_id = state.queue[0] if state.queue else None
        with folder.engine.connect() as connection:
            criteria_version = criteria_repo.get_version(
                connection, state.round.criteria_version_id
            )
        values: dict[str, Any] = {
            "state": state,
            "versions": version_numbers(),
            "ai_round": ai_context(state.round.id),
            "criteria": criteria_version,
            "values": pilot_view.value_labels(),
            "ref": None,
            "error": error,
            "message": message,
        }
        if reference_id is not None:
            values |= {
                "ref": enriched_reference(folder, reference_id),
                "previous": state.previous[reference_id],
                "a": state.ai[reference_id],
            }
        values |= {
            "full_text": state.round.stage is Stage.FULL_TEXT,
            "check_labels": fulltext_view.check_labels(),
        }
        return render(request, "tri_reevaluation.html", values, status_code=status_code)

    @app.get("/tri/reevaluation/{impact_id}", response_class=HTMLResponse)
    def show_reassessment(request: Request, impact_id: str, ok: str = "") -> HTMLResponse:
        messages = {
            "decision": _("Decision recorded."),
            "fin": _("Reassessment completed."),
            "lot": _("AI screening started."),
            "suivi": _("Following the running batches."),
        }
        return reassessment_page(request, impact_id, message=messages.get(ok))

    @app.post("/tri/reevaluation/{impact_id}")
    async def verify_reference(request: Request, impact_id: str, _csrf: Csrf) -> Response:
        reference_id, value, cited, note = decision_form(await request.form())
        if value is None:
            return reassessment_page(
                request, impact_id, error=_("Choose a decision."), status_code=422
            )
        try:
            await run_in_threadpool(
                reassessment.verify,
                folder,
                impact_id,
                reference_id,
                value,
                criteria_cited=cited,
                rationale=note,
                now=now,
                tool_version=context.tool_version,
            )
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        except _VERIFY_ERRORS as error:
            return reassessment_page(
                request, impact_id, error=decision_error(error), status_code=422
            )
        return see_other(f"/tri/reevaluation/{impact_id}?ok=decision")

    @app.post("/tri/reevaluation/{impact_id}/terminer")
    def complete_reassessment(request: Request, impact_id: str, _csrf: Csrf) -> Response:
        try:
            reassessment.complete(folder, impact_id, now=now, tool_version=context.tool_version)
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        except reassessment.ReassessmentNotFinishedError as error:
            return reassessment_page(request, impact_id, error=str(error), status_code=422)
        return see_other(f"/tri/reevaluation/{impact_id}?ok=fin")

    # --- Protocol ---------------------------------------------------------------------

    def protocol_page(
        request: Request,
        *,
        error: str | None = None,
        saved: bool = False,
        doi_value: str = "",
        date_value: str = "",
        status_code: int = 200,
    ) -> HTMLResponse:
        document = protocol_document(
            folder, language="fr", now=now, tool_version=context.tool_version
        )
        checklist = peters_checklist()
        statuses = checklist_status(document.blocks, checklist)
        current = registration.current_protocol_text(folder)
        return render(
            request,
            "protocole.html",
            {
                "registration": registration.current_registration(folder),
                "checklist": checklist,
                "checklist_rows": list(zip(checklist.items, statuses, strict=True)),
                "text": None if current is None else current.text,
                "free_sections": FREE_TEXT_SECTIONS,
                "doi_value": doi_value,
                "date_value": date_value,
                "error": error,
                "saved": saved,
            },
            status_code=status_code,
        )

    @app.get("/protocole", response_class=HTMLResponse)
    def show_protocol(request: Request, enregistre: int = 0) -> HTMLResponse:
        return protocol_page(request, saved=bool(enregistre))

    @app.post("/protocole/texte")
    async def save_protocol_text(request: Request, _csrf: Csrf) -> Response:
        form = await request.form()
        sections = {
            section: str(form.get(section.value, ""))
            for section in FREE_TEXT_SECTIONS
            if isinstance(form.get(section.value, ""), str)
        }
        await run_in_threadpool(
            registration.save_protocol_text,
            folder,
            ProtocolText(sections=sections),
            now=now,
            tool_version=context.tool_version,
        )
        return see_other("/protocole?enregistre=1#texte")

    @app.post("/protocole/enregistrement")
    def register(
        request: Request,
        _csrf: Csrf,
        doi: Annotated[str, Form()] = "",
        date_: Annotated[str, Form(alias="date")] = "",
    ) -> Response:
        try:
            registered_on = date.fromisoformat(date_)
        except ValueError:
            return protocol_page(
                request,
                error=_("Enter the registration date."),
                doi_value=doi,
                status_code=422,
            )
        try:
            registration.register_protocol(
                folder, doi, registered_on, now=now, tool_version=context.tool_version
            )
        except (
            registration.InvalidDoiError,
            registration.InvalidRegistrationDateError,
        ) as error:
            return protocol_page(
                request, error=str(error), doi_value=doi, date_value=date_, status_code=422
            )
        return see_other("/protocole#enregistrement")

    @app.get("/protocole/telecharger")
    def download_protocol(langue: str = "fr", format: str = "docx") -> Response:
        if langue not in EXPORT_LANGUAGES or format not in {"md", "docx"}:
            raise HTTPException(status_code=404, detail=_("Unknown export."))
        document = protocol_document(
            folder, language=langue, now=now, tool_version=context.tool_version
        )
        filename = f"protocole-{langue}.{format}"
        disposition = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if format == "md":
            return Response(
                render_markdown(document),
                media_type="text/markdown; charset=utf-8",
                headers=disposition,
            )
        return Response(
            render_docx(document),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=disposition,
        )

    # --- Full texts -------------------------------------------------------------------

    def fulltext_context() -> dict[str, Any]:
        report = retrieval.retrieval_report(folder)
        return {
            "report": report,
            "counts": report.counts,
            "job_running": background.running(fulltext_view.JOB),
            "job_error": background.error(fulltext_view.JOB),
            "fulltext_status_labels": fulltext_view.status_labels(),
            "origin_labels": fulltext_view.origin_labels(),
            "match_labels": fulltext_view.match_labels(),
        }

    def fulltext_page(
        request: Request,
        *,
        error: str | None = None,
        message: str | None = None,
        upload: retrieval.UploadReport | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        return render(
            request,
            "textes.html",
            fulltext_context() | {"error": error, "message": message, "upload": upload},
            status_code=status_code,
        )

    @app.get("/textes", response_class=HTMLResponse)
    def show_texts(request: Request, ajoute: int = 0, declare: int = 0) -> HTMLResponse:
        message = None
        if ajoute:
            message = _("Text added.")
        elif declare:
            message = _("Text declared not retrievable.")
        return fulltext_page(request, message=message)

    @app.get("/textes/etat", response_class=HTMLResponse)
    def texts_progress(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "_textes_etat.html", {"csrf_token": context.csrf_token} | fulltext_context()
        )

    @app.post("/textes/libres")
    def look_for_open_access(_csrf: Csrf, reessayer: Annotated[str, Form()] = "") -> Response:
        background.start(
            fulltext_view.JOB,
            lambda: retrieval.retrieve_open_access(
                folder,
                now=now,
                tool_version=context.tool_version,
                finder=open_access_finder,
                retry_not_found=bool(reessayer),
            ),
        )
        return see_other("/textes#libre-acces")

    @app.post("/textes/televerser")
    async def upload_texts(request: Request, _csrf: Csrf) -> Response:
        form = await request.form()
        files = [
            (item.filename, await item.read())
            for item in form.getlist("fichiers")
            if not isinstance(item, str) and item.filename
        ]
        if not files:
            return fulltext_page(request, error=_("Choose one or more PDF files."), status_code=422)
        report = await run_in_threadpool(
            retrieval.upload_files, folder, files, now=now, tool_version=context.tool_version
        )
        return fulltext_page(request, upload=report)

    @app.post("/textes/{reference_id}/televerser")
    async def upload_text(request: Request, reference_id: str, _csrf: Csrf) -> Response:
        form = await request.form()
        item = form.get("fichier")
        if item is None or isinstance(item, str) or not item.filename:
            return fulltext_page(request, error=_("Choose a PDF file."), status_code=422)
        content = await item.read()
        try:
            await run_in_threadpool(
                retrieval.add_upload,
                folder,
                reference_id,
                content,
                filename=item.filename,
                now=now,
                tool_version=context.tool_version,
            )
        except retrieval.FulltextError as error:
            return fulltext_page(request, error=str(error), status_code=422)
        return see_other(f"/textes?ajoute=1#reference-{reference_id}")

    @app.post("/textes/{reference_id}/introuvable")
    def declare_text_not_retrievable(
        request: Request, reference_id: str, _csrf: Csrf, raison: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            retrieval.declare_not_retrievable(
                folder, reference_id, raison, now=now, tool_version=context.tool_version
            )
        except retrieval.FulltextError as error:
            return fulltext_page(request, error=str(error), status_code=422)
        return see_other(f"/textes?declare=1#reference-{reference_id}")

    @app.get("/textes/manquants.csv")
    def download_missing() -> Response:
        path, _count = retrieval.export_missing(folder)
        return Response(
            path.read_text(encoding="utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="textes-manquants.csv"'},
        )

    def _document_row(reference_id: str) -> tuple[retrieval.RetrievalRow, FulltextDocument]:
        row = retrieval.retrieval_report(folder).row(reference_id)
        if row is None or row.document is None:
            raise HTTPException(status_code=404, detail=_("No full text for this reference."))
        return row, row.document

    # --- Extraction -------------------------------------------------------------------

    def extraction_page(
        request: Request,
        *,
        error: str | None = None,
        message: str | None = None,
        preview: CostPreview | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        state = prefill.extraction_state(folder)
        return render(
            request,
            "extraction.html",
            {
                "state": state,
                "pilot": validation.pilot_state(folder),
                "impact": extraction_impact.impact_state(folder),
                "archived": validation.archived_values(folder),
                "change_labels": grid_view.change_kind_labels(),
                "pilot_size": validation.PILOT_SIZE,
                "running": background.running(EXTRACTION_JOB),
                "job_error": background.error(EXTRACTION_JOB),
                "last_run": last_batches.get(EXTRACTION_JOB),
                "preview": preview,
                "ceiling": None if preview is None else pilot_view.batch_ceiling(preview.estimate),
                "error": error,
                "message": message,
            },
            status_code=status_code,
        )

    @app.get("/extraction", response_class=HTMLResponse)
    def show_extraction(request: Request, ok: str = "") -> HTMLResponse:
        messages = {
            "ia": _("Pre-filling started in the background."),
            "pilote": _("Studies of the pilot drawn: extract them without the AI."),
        }
        return extraction_page(request, message=messages.get(ok))

    @app.post("/extraction/ia/estimation")
    def estimate_extraction(request: Request, _csrf: Csrf) -> Response:
        try:
            preview = prefill.preview_ai(folder, factory=provider_factory)
        except _EXTRACTION_ERRORS as error:
            return extraction_page(request, error=str(error), status_code=422)
        return extraction_page(request, preview=preview)

    @app.post("/extraction/ia")
    def prefill_with_ai(
        request: Request, _csrf: Csrf, plafond: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            limit = pilot_view.parse_amount(plafond)
        except ValueError:
            return extraction_page(
                request, error=_("The ceiling must be a positive amount."), status_code=422
            )
        with folder.engine.connect() as connection:
            if screening_repo.latest_budget(connection) is None:
                error = str(screening_settings.BudgetNotSetError())
                return extraction_page(request, error=error, status_code=422)

        def work() -> None:
            last_batches[EXTRACTION_JOB] = prefill.run_ai(
                folder,
                batch_limit=limit,
                factory=provider_factory,
                now=now,
                tool_version=context.tool_version,
            )

        if not background.start(EXTRACTION_JOB, work):
            return extraction_page(
                request, error=_("An AI batch is already running."), status_code=422
            )
        return see_other("/extraction?ok=ia")

    def study_extraction_page(
        request: Request,
        reference_id: str,
        *,
        error: str | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        state = prefill.extraction_state(folder)
        study = next((s for s in state.studies if s.primary.id == reference_id), None)
        if study is None or state.grid is None:
            raise HTTPException(status_code=404, detail=_("Unknown study."))
        hidden = validation.blind(folder, reference_id)
        values = {
            code: value
            for code, value in study.values.items()
            if not hidden or value.reviewer_kind is ReviewerKind.HUMAN
        }
        return render(
            request,
            "extraction_etude.html",
            {
                "grid": state.grid,
                "study": study,
                "values": values,
                "blind": hidden,
                "type_labels": grid_view.type_labels(),
                "check_labels": fulltext_view.check_labels(),
                "status_labels": grid_view.value_status_labels(),
                "error": error,
                "message": message,
            },
            status_code=status_code,
        )

    @app.get("/extraction/{reference_id}", response_class=HTMLResponse)
    def show_study_extraction(request: Request, reference_id: str, ok: str = "") -> HTMLResponse:
        message = _("Value recorded.") if ok else None
        return study_extraction_page(request, reference_id, message=message)

    @app.post("/extraction/{reference_id}/{code}")
    async def decide_extracted_value(
        request: Request, reference_id: str, code: str, _csrf: Csrf
    ) -> Response:
        form = await request.form()
        action = str(form.get("action", ""))
        common: dict[str, Any] = {
            "note": str(form.get("note", "")),
            "now": now,
            "tool_version": context.tool_version,
        }
        try:
            if action == "valider":
                await run_in_threadpool(
                    validation.validate_value, folder, reference_id, code, **common
                )
            elif action == "confirmer":
                await run_in_threadpool(
                    validation.confirm_value, folder, reference_id, code, **common
                )
            elif action == "rejeter":
                await run_in_threadpool(
                    validation.reject_value, folder, reference_id, code, **common
                )
            else:
                raw_page = str(form.get("page", "")).strip()
                if raw_page and not (raw_page.isdigit() and int(raw_page) > 0):
                    return study_extraction_page(
                        request,
                        reference_id,
                        error=_("The page must be a positive whole number."),
                        status_code=422,
                    )
                given: list[JsonValue] = [str(v) for v in form.getlist("valeur")]
                value: JsonValue = given if len(given) > 1 else (given[0] if given else None)
                await run_in_threadpool(
                    validation.record_value,
                    folder,
                    reference_id,
                    code,
                    reported=form.get("rapporte") == "oui",
                    value=value,
                    quote=str(form.get("citation", "")),
                    page=int(raw_page) if raw_page else None,
                    **common,
                )
        except (validation.NotAStudyError, prefill.NoGridError) as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        except (validation.NoAIValueError, validation.NothingToConfirmError) as error:
            return study_extraction_page(request, reference_id, error=str(error), status_code=422)
        except InvalidValueError:
            return study_extraction_page(
                request,
                reference_id,
                error=_("The value does not fit the type of field %(code)s.") % {"code": code},
                status_code=422,
            )
        return see_other(f"/extraction/{reference_id}?ok=1#champ-{code}")

    @app.post("/extraction/pilote")
    def start_extraction_pilot(
        request: Request, _csrf: Csrf, taille: Annotated[str, Form()] = ""
    ) -> Response:
        size = int(taille) if taille.strip().isdigit() else 0
        if size < 1:
            return extraction_page(
                request, error=_("The number of studies must be at least 1."), status_code=422
            )
        try:
            validation.start_pilot(folder, size=size, now=now, tool_version=context.tool_version)
        except (prefill.NoGridError, validation.NotAStudyError) as error:
            return extraction_page(request, error=str(error), status_code=422)
        return see_other("/extraction?ok=pilote")

    @app.post("/extraction/export")
    def export_extracted_values(request: Request, _csrf: Csrf) -> Response:
        path, written = validation.export_extraction(folder)
        message = _("%(count)s values written to %(path)s.") % {
            "count": written,
            "path": path.relative_to(folder.path).as_posix(),
        }
        return extraction_page(request, message=message)

    # --- Synthesis ------------------------------------------------------------------

    def synthesis_page(
        request: Request,
        *,
        rows: str = "",
        columns: str = "",
        sparse: int = synthesis_maps.SPARSE_MAX,
        error: str | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        try:
            grid, studies = synthesis_maps.study_data(folder)
        except prefill.NoGridError:
            return render(request, "synthese.html", {"grid": None}, status_code=status_code)
        labels = synthesis_maps.category_labels("fr")
        tables = [synthesis_frequency(f, studies, labels) for f in grid.sorted_fields()]
        crossed, found, svg, comments = None, [], "", {}
        if rows and columns and rows != columns:
            try:
                crossed, _studies = synthesis_maps.cross(folder, rows, columns)
            except synthesis_maps.UnknownFieldError as unknown:
                raise HTTPException(status_code=404, detail=str(unknown)) from unknown
            found = list(synthesis_gaps(crossed, sparse_max=sparse))
            context_map = MapContext(
                project_title=project.title, language="fr",
                tool_version=context.tool_version, generated_at=now(),
            )  # fmt: skip
            svg = map_svg(crossed, found, context_map)
            comments = synthesis_maps.comments(folder, rows, columns)
        return render(
            request,
            "synthese.html",
            {
                "grid": grid,
                "studies": studies,
                "tables": tables,
                "rows": rows,
                "columns": columns,
                "sparse": sparse,
                "crossed": crossed,
                "gaps": found,
                "svg": Markup(svg),  # noqa: S704 - built here, every text escaped
                "comments": comments,
                "labels": {s.id: s.label for s in studies},
                "error": error,
                "message": message,
            },
            status_code=status_code,
        )

    @app.get("/synthese", response_class=HTMLResponse)
    def show_synthesis(
        request: Request, lignes: str = "", colonnes: str = "", seuil: str = ""
    ) -> HTMLResponse:
        sparse = int(seuil) if seuil.isdigit() else synthesis_maps.SPARSE_MAX
        error = None
        if lignes and lignes == colonnes:
            error = _("Choose two different fields.")
        return synthesis_page(
            request, rows=lignes, columns=colonnes, sparse=sparse, error=error,
            status_code=422 if error else 200,
        )  # fmt: skip

    @app.post("/synthese/lacune")
    def comment_gap(
        request: Request,
        _csrf: Csrf,
        lignes: Annotated[str, Form()],
        colonnes: Annotated[str, Form()],
        ligne: Annotated[str, Form()],
        colonne: Annotated[str, Form()],
        commentaire: Annotated[str, Form()] = "",
        seuil: Annotated[str, Form()] = "",
    ) -> Response:
        try:
            synthesis_maps.comment_gap(
                folder, lignes, colonnes, ligne, colonne, commentaire, now=now,
                tool_version=context.tool_version,
            )  # fmt: skip
        except (synthesis_maps.UnknownFieldError, prefill.NoGridError) as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        query = urlencode({"lignes": lignes, "colonnes": colonnes, "seuil": seuil})
        return see_other(f"/synthese?{query}#lacunes")

    @app.post("/synthese/export")
    def export_synthesis(
        request: Request,
        _csrf: Csrf,
        lignes: Annotated[str, Form()] = "",
        colonnes: Annotated[str, Form()] = "",
        seuil: Annotated[str, Form()] = "",
    ) -> Response:
        sparse = int(seuil) if seuil.isdigit() else synthesis_maps.SPARSE_MAX
        crossing = [(lignes, colonnes)] if lignes and colonnes and lignes != colonnes else []
        try:
            written = synthesis_maps.export_tables(folder, language="fr", crosses=crossing, now=now)
            for rows, columns in crossing:
                written += synthesis_maps.export_map(
                    folder, rows, columns, language="fr", sparse_max=sparse, now=now,
                    tool_version=context.tool_version,
                )  # fmt: skip
        except (synthesis_maps.UnknownFieldError, prefill.NoGridError) as error:
            return synthesis_page(request, error=str(error), status_code=422)
        message = _("Files written in %(path)s: %(count)s.") % {
            "path": "exports/synthese",
            "count": len(written),
        }
        return synthesis_page(
            request, rows=lignes, columns=colonnes, sparse=sparse, message=message
        )

    # --- Narrative synthesis --------------------------------------------------------

    def narrative_page(
        request: Request,
        code: str,
        *,
        preview: CostPreview | None = None,
        error: str | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        try:
            state = synthesis_narrative.narrative_state(folder)
            target = state.field(code)
        except (prefill.NoGridError, synthesis_narrative.UnknownFieldError) as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        job = NARRATIVE_JOB.format(code=code)
        shown = target.current.sentences if target.current is not None else ()
        return render(
            request,
            "synthese_narratif_champ.html",
            {
                "state": state,
                "target": target,
                "labels": state.labels,
                "rows": [*shown, None, None],
                "running": background.running(job),
                "job_error": background.error(job),
                "preview": preview,
                "ceiling": None if preview is None else pilot_view.batch_ceiling(preview.estimate),
                "error": error,
                "message": message,
            },
            status_code=status_code,
        )

    @app.get("/synthese/narratif", response_class=HTMLResponse)
    def show_narrative(request: Request, message: str = "") -> HTMLResponse:
        try:
            state = synthesis_narrative.narrative_state(folder)
        except prefill.NoGridError:
            return render(request, "synthese_narratif.html", {"state": None})
        return render(
            request, "synthese_narratif.html", {"state": state, "message": message or None}
        )

    @app.post("/synthese/narratif/export")
    def export_narrative(request: Request, _csrf: Csrf) -> Response:
        try:
            written = synthesis_narrative.export_narrative(
                folder, language="fr", now=now, tool_version=context.tool_version
            )
        except prefill.NoGridError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        message = _("Files written in %(path)s: %(count)s.") % {
            "path": "exports/synthese",
            "count": len(written),
        }
        return show_narrative(request, message=message)

    @app.get("/synthese/narratif/{code}", response_class=HTMLResponse)
    def show_field_narrative(request: Request, code: str, ok: str = "") -> HTMLResponse:
        messages = {
            "ia": _("The AI is drafting the synthesis in the background."),
            "revision": _("Synthesis recorded."),
        }
        return narrative_page(request, code, message=messages.get(ok))

    @app.post("/synthese/narratif/{code}/ia/estimation")
    def estimate_narrative(request: Request, code: str, _csrf: Csrf) -> Response:
        try:
            preview = synthesis_narrative.preview_ai(folder, code, factory=provider_factory)
        except _NARRATIVE_ERRORS as error:
            return narrative_page(request, code, error=str(error), status_code=422)
        return narrative_page(request, code, preview=preview)

    @app.post("/synthese/narratif/{code}/ia")
    def draft_narrative(
        request: Request, code: str, _csrf: Csrf, plafond: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            limit = pilot_view.parse_amount(plafond)
        except ValueError:
            return narrative_page(
                request, code, error=_("The ceiling must be a positive amount."), status_code=422
            )
        with folder.engine.connect() as connection:
            if screening_repo.latest_budget(connection) is None:
                error = str(screening_settings.BudgetNotSetError())
                return narrative_page(request, code, error=error, status_code=422)

        def work() -> None:
            synthesis_narrative.draft_with_ai(
                folder, code, ceiling=limit, factory=provider_factory, now=now,
                tool_version=context.tool_version,
            )  # fmt: skip

        if not background.start(NARRATIVE_JOB.format(code=code), work):
            return narrative_page(
                request, code, error=_("An AI batch is already running."), status_code=422
            )
        return see_other(f"/synthese/narratif/{code}?ok=ia")

    @app.post("/synthese/narratif/{code}")
    async def revise_narrative(request: Request, code: str, _csrf: Csrf) -> Response:
        form = await request.form()
        raw = str(form.get("nombre", "0"))
        sentences = []
        for index in range(int(raw) if raw.isdigit() else 0):
            text_ = str(form.get(f"phrase-{index}", "")).strip()
            if not text_:
                continue
            cited = tuple(str(v) for v in form.getlist(f"etudes-{index}"))
            if not cited:
                return narrative_page(
                    request, code,
                    error=_("Each sentence must rest on at least one study (sentence %(n)s).")
                    % {"n": index + 1},
                    status_code=422,
                )  # fmt: skip
            sentences.append(NarrativeSentence(text=text_, study_ids=cited))
        try:
            await run_in_threadpool(
                synthesis_narrative.revise, folder, code, sentences, now=now,
                tool_version=context.tool_version,
            )  # fmt: skip
        except (prefill.NoGridError, synthesis_narrative.UnknownFieldError) as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        except UnsupportedSentenceError:
            return narrative_page(
                request, code,
                error=_("Write at least one sentence, each resting on included studies."),
                status_code=422,
            )  # fmt: skip
        return see_other(f"/synthese/narratif/{code}?ok=revision")

    # --- Extraction grid --------------------------------------------------------------

    def grid_page(
        request: Request,
        *,
        error: str | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        state = extraction_grid.grid_state(folder)
        versions = list(state.versions)
        history = [
            (v, None if i == 0 else grid_diff(versions[i - 1], v)) for i, v in enumerate(versions)
        ]
        draft_diff = (
            None
            if state.draft is None or state.active is None
            else grid_diff(state.active, state.draft)
        )
        return render(
            request,
            "grille.html",
            {
                "state": state,
                "history": list(reversed(history)),
                "draft_diff": draft_diff,
                "type_labels": grid_view.type_labels(),
                "changed_labels": grid_view.changed_labels(),
                "template": grid_template(),
                "error": error,
                "message": message,
            },
            status_code=status_code,
        )  # fmt: skip

    def grid_form(
        form: Any,  # noqa: ANN401 - Starlette form data
    ) -> dict[str, Any]:
        def lines(name: str) -> list[str]:
            return [line for line in str(form.get(name, "")).splitlines() if line.strip()]

        return {
            "label": str(form.get("libelle", "")),
            "type": FieldType(str(form.get("type", ""))),
            "definition": str(form.get("definition", "")),
            "guidance": str(form.get("consignes", "")),
            "examples": lines("exemples"),
            "choices": lines("choix"),
        }

    grid_errors = (
        ValueError,
        extraction_grid.UnknownFieldError,
        extraction_grid.NoDraftError,
    )

    def grid_error(error: Exception) -> str:
        if isinstance(error, ValidationError):
            return _(
                "A choice field needs at least two distinct choices, one per line; other "
                "fields have no choices; a field needs a name."
            )
        if isinstance(error, MissingRationaleError):
            return _("A new version of the grid needs a rationale.")
        if isinstance(error, EmptyCriteriaError):
            return _("The grid needs at least one field.")
        return str(error) or _("This change cannot be made.")

    @app.get("/grille", response_class=HTMLResponse)
    def show_grid(request: Request, ok: str = "") -> HTMLResponse:
        messages = {
            "ajout": _("Field added to the draft."),
            "modele": _("Fields of the starting grid added to the draft."),
            "modif": _("Field modified in the draft."),
            "retrait": _("Field removed from the draft."),
            "activation": _("The new version of the grid is in force."),
            "abandon": _("Draft discarded."),
        }
        return grid_page(request, message=messages.get(ok))

    @app.post("/grille/ajouter")
    async def add_grid_field(request: Request, _csrf: Csrf) -> Response:
        try:
            extraction_grid.add_field(
                folder, **grid_form(await request.form()), now=now,
                tool_version=context.tool_version,
            )  # fmt: skip
        except grid_errors as error:
            return grid_page(request, error=grid_error(error), status_code=422)
        return see_other("/grille?ok=ajout#brouillon")

    @app.post("/grille/modele")
    def add_grid_template(_csrf: Csrf) -> Response:
        extraction_grid.add_template(folder, now=now, tool_version=context.tool_version)
        return see_other("/grille?ok=modele#brouillon")

    @app.post("/grille/{code}/modifier")
    async def update_grid_field(request: Request, code: str, _csrf: Csrf) -> Response:
        try:
            extraction_grid.update_field(
                folder, code, **grid_form(await request.form()), now=now,
                tool_version=context.tool_version,
            )  # fmt: skip
        except grid_errors as error:
            return grid_page(request, error=grid_error(error), status_code=422)
        return see_other(f"/grille?ok=modif#champ-{code}")

    @app.post("/grille/{code}/retirer")
    def remove_grid_field(request: Request, code: str, _csrf: Csrf) -> Response:
        try:
            extraction_grid.remove_field(folder, code, now=now, tool_version=context.tool_version)
        except grid_errors as error:
            return grid_page(request, error=grid_error(error), status_code=422)
        return see_other("/grille?ok=retrait#brouillon")

    @app.post("/grille/activer")
    def activate_grid(
        request: Request, _csrf: Csrf, justification: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            extraction_grid.activate_draft(
                folder, rationale=justification, now=now, tool_version=context.tool_version
            )
        except (*grid_errors, EmptyCriteriaError) as error:
            return grid_page(request, error=grid_error(error), status_code=422)
        return see_other("/grille?ok=activation")

    @app.post("/grille/abandonner")
    def discard_grid_draft(request: Request, _csrf: Csrf) -> Response:
        try:
            extraction_grid.discard_draft(folder, now=now, tool_version=context.tool_version)
        except extraction_grid.NoDraftError as error:
            return grid_page(request, error=str(error), status_code=422)
        return see_other("/grille?ok=abandon")

    # --- Studies and their reports -------------------------------------------------

    def studies_page(
        request: Request,
        *,
        error: str | None = None,
        message: str | None = None,
        preview: CostPreview | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        state = studies.study_state(folder)
        reports = {
            ref: reference for ref, (reference, _doc) in studies.included_reports(folder).items()
        }
        return render(
            request,
            "etudes.html",
            {
                "state": state,
                "reports": reports,
                "pending": [same_pair(c.reference_a_id, c.reference_b_id) for c in state.pending],
                "running": background.running(STUDY_JOB),
                "job_error": background.error(STUDY_JOB),
                "last_run": last_batches.get(STUDY_JOB),
                "preview": preview,
                "ceiling": None if preview is None else pilot_view.batch_ceiling(preview.estimate),
                "verdict_labels": fulltext_view.verdict_labels(),
                "check_labels": fulltext_view.check_labels(),
                "rule_labels": fulltext_view.rule_labels(),
                "error": error,
                "message": message,
            },
            status_code=status_code,
        )

    @app.get("/textes/etudes", response_class=HTMLResponse)
    def show_studies(request: Request, ok: str = "") -> HTMLResponse:
        messages = {
            "decision": _("Decision recorded."),
            "principal": _("Primary report chosen."),
            "ia": _("AI examination started in the background."),
        }
        return studies_page(request, message=messages.get(ok))

    @app.post("/textes/etudes/ia/estimation")
    def estimate_studies_ai(request: Request, _csrf: Csrf) -> Response:
        try:
            preview = studies.preview_ai(folder, factory=provider_factory)
        except _AI_ERRORS as error:
            return studies_page(request, error=str(error), status_code=422)
        return studies_page(request, preview=preview)

    @app.post("/textes/etudes/ia")
    def examine_pairs_with_ai(
        request: Request, _csrf: Csrf, plafond: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            limit = pilot_view.parse_amount(plafond)
        except ValueError:
            return studies_page(
                request, error=_("The ceiling must be a positive amount."), status_code=422
            )
        with folder.engine.connect() as connection:
            if screening_repo.latest_budget(connection) is None:
                error = str(screening_settings.BudgetNotSetError())
                return studies_page(request, error=error, status_code=422)

        def work() -> None:
            last_batches[STUDY_JOB] = studies.run_ai(
                folder,
                batch_limit=limit,
                factory=provider_factory,
                now=now,
                tool_version=context.tool_version,
            )

        if not background.start(STUDY_JOB, work):
            return studies_page(
                request, error=_("An AI batch is already running."), status_code=422
            )
        return see_other("/textes/etudes?ok=ia")

    @app.post("/textes/etudes/decision")
    def decide_study_link(
        request: Request,
        _csrf: Csrf,
        a: Annotated[str, Form()] = "",
        b: Annotated[str, Form()] = "",
        issue: Annotated[str, Form()] = "",
        note: Annotated[str, Form()] = "",
    ) -> Response:
        try:
            outcome = LinkOutcome(issue)
        except ValueError:
            return studies_page(request, error=_("Choose a decision."), status_code=422)
        try:
            studies.decide(
                folder, a, b, outcome, note=note, now=now, tool_version=context.tool_version
            )
        except studies.NotIncludedError as error:
            return studies_page(request, error=str(error), status_code=422)
        return see_other("/textes/etudes?ok=decision")

    @app.post("/textes/etudes/principal")
    def choose_primary_report(
        request: Request, _csrf: Csrf, reference: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            studies.choose_primary(folder, reference, now=now, tool_version=context.tool_version)
        except studies.NotIncludedError as error:
            return studies_page(request, error=str(error), status_code=422)
        return see_other("/textes/etudes?ok=principal")

    # --- Full-text screening ------------------------------------------------------------

    def text_job(round_id: str) -> str:
        return f"texte-ia-{round_id}"

    def fulltext_screening_page(
        request: Request,
        *,
        error: str | None = None,
        message: str | None = None,
        preview: CostPreview | None = None,
        preview_round: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        trial = fulltext_screening.pilot_round(folder)
        started = fulltext_screening.main_round(folder)
        pilot_state = None if trial is None else fulltext_screening.pilot_state(folder, trial.id)
        state = None if started is None else fulltext_screening.main_state(folder)
        texts = fulltext_screening.screenable_texts(folder)
        new_texts = 0 if state is None else len(set(texts) - set(state.members))
        jobs = [r.id for r in (trial, started) if r is not None]
        with folder.engine.connect() as connection:
            budget = screening_repo.latest_budget(connection)
        impact_values: dict[str, Any] = {}
        if started is not None:
            impact_values = {
                "to_assess": reassessment.next_version_to_assess(folder, started.id),
                "impacts": reassessment.impacts(folder, started.id),
                "versions": version_numbers(),
            }
        return render(
            request,
            "textes_tri.html",
            {
                "texts": len(texts),
                "trial": trial,
                "pilot": pilot_state,
                "started": started,
                "state": state,
                "new_texts": new_texts,
                "pilot_complete": pilot_state is not None and pilot_state.complete,
                "running": {r: background.running(text_job(r)) for r in jobs},
                "job_errors": {r: background.error(text_job(r)) for r in jobs},
                "last_runs": {r: last_batches.get(r) for r in jobs},
                "budget": budget,
                "preview": preview,
                "preview_round": preview_round,
                "ceiling": None if preview is None else pilot_view.batch_ceiling(preview.estimate),
                "values": pilot_view.value_labels(),
                "error": error,
                "message": message,
            }
            | impact_values,
            status_code=status_code,
        )

    @app.get("/textes/tri", response_class=HTMLResponse)
    def show_text_screening(request: Request, ok: str = "") -> HTMLResponse:
        messages = {
            "pilote": _("Pilot drawn."),
            "tri": _("Full-text screening started."),
            "ajout": _("New texts added at the end of the screening."),
            "ia": _("AI screening started in the background."),
        }
        return fulltext_screening_page(request, message=messages.get(ok))

    @app.post("/textes/tri/pilote")
    def start_text_pilot(request: Request, _csrf: Csrf) -> Response:
        try:
            fulltext_screening.start_pilot(folder, now=now, tool_version=context.tool_version)
        except (fulltext_screening.NoTextsError, pilot.NoActiveCriteriaError) as error:
            return fulltext_screening_page(request, error=str(error), status_code=422)
        return see_other("/textes/tri?ok=pilote#pilote")

    @app.post("/textes/tri/commencer")
    def start_text_screening(
        request: Request, _csrf: Csrf, mode: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            chosen = ScreeningMode(mode)
        except ValueError:
            return fulltext_screening_page(
                request, error=_("Choose the mode of the screening."), status_code=422
            )
        try:
            fulltext_screening.start_main(
                folder, chosen, now=now, tool_version=context.tool_version
            )
        except (
            fulltext_screening.NoTextsError,
            fulltext_screening.FulltextMainExistsError,
            pilot.NoActiveCriteriaError,
        ) as error:
            return fulltext_screening_page(request, error=str(error), status_code=422)
        return see_other("/textes/tri?ok=tri#principal")

    @app.post("/textes/tri/impact")
    def assess_text_impact(
        request: Request, _csrf: Csrf, toutes: Annotated[str, Form()] = ""
    ) -> Response:
        started = fulltext_screening.main_round(folder)
        if started is None:
            raise HTTPException(
                status_code=404, detail=_("The full-text screening has not started.")
            )
        try:
            impact = reassessment.assess(
                folder,
                started.id,
                sample_clarifications=not toutes,
                now=now,
                tool_version=context.tool_version,
            )
        except reassessment.NothingToAssessError as error:
            return fulltext_screening_page(request, error=str(error), status_code=422)
        if impact.reassessment_round_id is None:
            return see_other("/textes/tri#changements")
        return see_other(f"/tri/reevaluation/{impact.id}")

    @app.post("/textes/tri/ajouter")
    def add_texts_to_screening(_csrf: Csrf) -> Response:
        fulltext_screening.add_new_texts(folder, now=now, tool_version=context.tool_version)
        return see_other("/textes/tri?ok=ajout#principal")

    @app.post("/textes/tri/{round_id}/ia/estimation")
    def estimate_text_ai(request: Request, round_id: str, _csrf: Csrf) -> Response:
        try:
            screening = fulltext_screening.round_of(folder, round_id)
            if screening.kind is RoundKind.MAIN:  # the main round goes through batches
                preview = batch_ai.preview(folder, round_id, factory=provider_factory)
            else:
                preview = fulltext_screening.preview_ai(folder, round_id, factory=provider_factory)
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        except _BATCH_ERRORS as error:
            return fulltext_screening_page(request, error=str(error), status_code=422)
        return fulltext_screening_page(request, preview=preview, preview_round=round_id)

    @app.post("/textes/tri/{round_id}/ia")
    def screen_texts_with_ai(
        request: Request, round_id: str, _csrf: Csrf, plafond: Annotated[str, Form()] = ""
    ) -> Response:
        try:
            screening = fulltext_screening.round_of(folder, round_id)
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        try:
            limit = pilot_view.parse_amount(plafond)
        except ValueError:
            return fulltext_screening_page(
                request, error=_("The ceiling must be a positive amount."), status_code=422
            )
        with folder.engine.connect() as connection:
            if screening_repo.latest_budget(connection) is None:
                error = str(screening_settings.BudgetNotSetError())
                return fulltext_screening_page(request, error=error, status_code=422)
        if screening.kind is RoundKind.MAIN and not fulltext_screening.pilot_complete(folder):
            error = str(fulltext_screening.PilotRequiredError())
            return fulltext_screening_page(request, error=error, status_code=422)

        def work() -> None:
            if screening.kind is RoundKind.MAIN:
                run_batches(round_id, limit)
                return
            last_batches[round_id] = fulltext_screening.run_ai(
                folder,
                round_id,
                batch_limit=limit,
                factory=provider_factory,
                now=now,
                tool_version=context.tool_version,
            )

        if not background.start(text_job(round_id), work):
            return fulltext_screening_page(
                request, error=_("An AI batch is already running on this round."), status_code=422
            )
        return see_other("/textes/tri?ok=ia")

    def text_decision_page(
        request: Request,
        round_id: str,
        *,
        reference_id: str | None = None,
        skipped: Sequence[str] = (),
        error: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        try:
            screening = fulltext_screening.round_of(folder, round_id)
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        if screening.kind is RoundKind.MAIN:
            state = fulltext_screening.main_state(folder)
            chosen = reference_id or fulltext_screening.next_text(state, skip=skipped)
            ai = None if chosen is None else state.visible_ai(chosen)
            done, total = len(set(state.members) & state.human.keys()), len(state.members)
            assisted = state.assisted
        else:
            pilot_state = fulltext_screening.pilot_state(folder, round_id)
            members = pilot_state.round.reference_ids
            chosen = reference_id or next(
                (r for r in members if r not in pilot_state.human and r not in skipped), None
            )
            ai, assisted = None, False
            done, total = len(pilot_state.human), len(members)
        report = retrieval.retrieval_report(folder)
        row = None if chosen is None else report.row(chosen)
        pages: list[tuple[Any, bool]] = []
        if row is not None and row.document is not None:
            text = retrieval.paged_text(folder, row.document)
            body = {page.number: page.text for page in text.body()}
            pages = [(page, body[page.number] != page.text) for page in text.pages]
        return render(
            request,
            "texte_trier.html",
            {
                "screening": screening,
                "row": row,
                "pages": pages,
                "a": ai,
                "assisted": assisted,
                "done": done,
                "total": total,
                "skipped": ",".join(skipped),
                "criteria": fulltext_screening.criteria_of_round(folder, screening),
                "values": pilot_view.value_labels(),
                "check_labels": fulltext_view.check_labels(),
                "error": error,
            },
            status_code=status_code,
        )

    @app.get("/textes/tri/{round_id}/trier", response_class=HTMLResponse)
    def screen_next_text(
        request: Request, round_id: str, ref: str = "", passer: str = ""
    ) -> HTMLResponse:
        return text_decision_page(
            request, round_id, reference_id=ref or None, skipped=screening_view.skip_list(passer)
        )

    @app.post("/textes/tri/{round_id}/decision")
    async def decide_text(request: Request, round_id: str, _csrf: Csrf) -> Response:
        reference_id, value, cited, note = decision_form(await request.form())
        if value is None:
            return text_decision_page(
                request, round_id, reference_id=reference_id, error=_("Choose a decision."),
                status_code=422,
            )  # fmt: skip
        try:
            await run_in_threadpool(
                fulltext_screening.record_decision,
                folder,
                round_id,
                reference_id,
                value,
                criteria_cited=cited,
                rationale=note,
                now=now,
                tool_version=context.tool_version,
            )
        except pilot.UnknownRoundError as unknown:
            raise HTTPException(status_code=404, detail=str(unknown)) from unknown
        except _TEXT_DECISION_ERRORS as error:
            return text_decision_page(
                request, round_id, reference_id=reference_id, error=decision_error(error),
                status_code=422,
            )  # fmt: skip
        return see_other(f"/textes/tri/{round_id}/trier")

    def text_reconciliation_page(
        request: Request,
        *,
        error: str | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        if fulltext_screening.main_round(folder) is None:
            raise HTTPException(
                status_code=404, detail=_("The full-text screening has not started.")
            )
        state = fulltext_screening.main_state(folder)
        reference_id = state.queue[0] if state.queue else None
        values: dict[str, Any] = {
            "row": None,
            "left": len(state.queue),
            "criteria": fulltext_screening.criteria_of_round(folder, state.round),
            "values": pilot_view.value_labels(),
            "check_labels": fulltext_view.check_labels(),
            "error": error,
            "message": message,
        }
        if reference_id is not None:
            values |= {
                "row": retrieval.retrieval_report(folder).row(reference_id),
                "human": state.human[reference_id],
                "a": state.visible_ai(reference_id),
            }
        return render(request, "texte_reconciliation.html", values, status_code=status_code)

    @app.get("/textes/tri/reconciliation", response_class=HTMLResponse)
    def show_text_reconciliation(request: Request, ok: int = 0) -> HTMLResponse:
        return text_reconciliation_page(
            request, message=_("Final decision recorded.") if ok else None
        )

    @app.post("/textes/tri/reconciliation")
    async def reconcile_text(request: Request, _csrf: Csrf) -> Response:
        reference_id, value, cited, note = decision_form(await request.form())
        if value is None:
            return text_reconciliation_page(request, error=_("Choose a decision."), status_code=422)
        try:
            await run_in_threadpool(
                fulltext_screening.reconcile,
                folder,
                reference_id,
                value,
                criteria_cited=cited,
                rationale=note,
                now=now,
                tool_version=context.tool_version,
            )
        except _TEXT_RECONCILE_ERRORS as error:
            return text_reconciliation_page(request, error=decision_error(error), status_code=422)
        return see_other("/textes/tri/reconciliation?ok=1")

    @app.get("/textes/{reference_id}", response_class=HTMLResponse)
    def show_text(request: Request, reference_id: str) -> HTMLResponse:
        row, document = _document_row(reference_id)
        text = retrieval.paged_text(folder, document)
        body = {page.number: page.text for page in text.body()}
        return render(
            request,
            "texte.html",
            {
                "row": row,
                "pages": [(page, body[page.number] != page.text) for page in text.pages],
                "origin_labels": fulltext_view.origin_labels(),
            },
        )

    @app.get("/textes/{reference_id}/pdf")
    def download_pdf(reference_id: str) -> Response:
        _row, document = _document_row(reference_id)
        return FileResponse(
            folder.path / retrieval.TEXT_FOLDER / f"{document.sha256}.pdf",
            media_type="application/pdf",
            filename=f"{reference_id}.pdf",
        )

    # --- Reports ----------------------------------------------------------------------

    def archives() -> list[str]:
        exports = folder.path / "exports"
        names = (p.name for p in exports.glob("archive-*.zip")) if exports.is_dir() else ()
        return sorted((n for n in names if ARCHIVE_NAME.fullmatch(n)), reverse=True)

    def reports_page(
        request: Request,
        *,
        error: str | None = None,
        archive: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        numbers = flow_report(folder, now=now, tool_version=context.tool_version).numbers
        return render(
            request,
            "rapports.html",
            {
                "numbers": numbers,
                "pending": separator(DEFAULT_LOCALE).join(
                    pending_items(_, numbers.pending, DEFAULT_LOCALE)
                ),
                "archives": archives(),
                "archive": archive,
                "retained": len(retained_references(folder)),
                "error": error,
            },
            status_code=status_code,
        )

    @app.get("/rapports", response_class=HTMLResponse)
    def show_reports(request: Request, archive: str = "") -> HTMLResponse:
        return reports_page(request, archive=archive if archive in archives() else None)

    @app.get("/rapports/diagramme")
    def flow_diagram(langue: str = "fr", telecharger: int = 0) -> Response:
        if langue not in EXPORT_LANGUAGES:
            raise HTTPException(status_code=404, detail=_("Unknown export."))
        report = flow_report(folder, now=now, tool_version=context.tool_version)
        svg = render_flow_svg(report.numbers, flow_template(), report.context, language=langue)
        headers = (
            {"Content-Disposition": f'attachment; filename="diagramme-{langue}.svg"'}
            if telecharger
            else {}
        )
        return Response(svg, media_type="image/svg+xml; charset=utf-8", headers=headers)

    @app.get("/rapports/methode")
    def download_methods(langue: str = "fr", format: str = "docx") -> Response:
        if langue not in EXPORT_LANGUAGES or format not in {"md", "docx"}:
            raise HTTPException(status_code=404, detail=_("Unknown export."))
        document = methods_document(
            folder, language=langue, now=now, tool_version=context.tool_version
        )
        filename = f"methode-{langue}.{format}"
        disposition = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if format == "md":
            return Response(
                render_markdown(document),
                media_type="text/markdown; charset=utf-8",
                headers=disposition,
            )
        return Response(
            render_docx(document),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=disposition,
        )

    @app.get("/rapports/retenues")
    def download_retained(format: str = "ris") -> Response:
        if format not in {"ris", "csv"}:
            raise HTTPException(status_code=404, detail=_("Unknown export."))
        items = retained_references(folder)
        media = "application/x-research-info-systems" if format == "ris" else "text/csv"
        return Response(
            write_ris(items) if format == "ris" else write_csv(items),
            media_type=f"{media}; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="references-retenues.{format}"'},
        )

    @app.post("/rapports/archive")
    def create_archive(
        request: Request, _csrf: Csrf, sorte: Annotated[str, Form()] = ""
    ) -> Response:
        if sorte not in {k.value for k in ArchiveKind}:
            return reports_page(request, error=_("Choose the kind of archive."), status_code=422)
        try:
            result = export_archive(
                folder, kind=ArchiveKind(sorte), now=now, tool_version=context.tool_version
            )
        except SecretInArchiveError as error:
            return reports_page(request, error=str(error), status_code=422)
        return see_other(f"/rapports?archive={result.path.name}#archive")

    @app.get("/rapports/archives/{name}")
    def download_archive(name: str) -> Response:
        if name not in archives():
            raise HTTPException(status_code=404, detail=_("Unknown export."))
        return FileResponse(
            folder.path / "exports" / name, media_type="application/zip", filename=name
        )

    # --- Journal ----------------------------------------------------------------------

    def journal_page(
        request: Request, *, error: str | None = None, status_code: int = 200
    ) -> HTMLResponse:
        entries = notes.journal_entries(folder)
        return render(
            request,
            "journal.html",
            {
                "entries": list(reversed(entries)),
                "check": verify_chain(entries),
                "error": error,
            },
            status_code=status_code,
        )

    @app.get("/journal", response_class=HTMLResponse)
    def show_journal(request: Request) -> HTMLResponse:
        return journal_page(request)

    @app.post("/journal/notes")
    def add_note(request: Request, _csrf: Csrf, note: Annotated[str, Form()] = "") -> Response:
        try:
            notes.add_note(folder, note, now=now, tool_version=context.tool_version)
        except notes.EmptyNoteError as error:
            return journal_page(request, error=str(error), status_code=422)
        return see_other("/journal")

    @app.exception_handler(HTTPException)
    def http_error(request: Request, error: HTTPException) -> HTMLResponse:
        return render(
            request,
            "erreur.html",
            {"status": error.status_code, "detail": error.detail},
            status_code=error.status_code,
        )

    return app
