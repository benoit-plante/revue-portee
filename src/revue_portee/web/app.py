"""Local web application (FastAPI + Jinja2 + HTMX), French interface.

The server only answers on 127.0.0.1 (ENF-SEC-06). Because any web page open in the
browser could still send requests to it, every form carries a per-process token and
requests with a foreign ``Host`` or ``Origin`` are refused (CSRF, DNS rebinding).
"""

import secrets
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from importlib.resources import files
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from revue_portee.ai.costs import UnknownPriceError
from revue_portee.ai.providers import ProviderFactory, UnknownProviderError
from revue_portee.ai.providers.anthropic import UnsupportedParameterError
from revue_portee.ai.settings import TaskNotAvailableError
from revue_portee.clock import utc_now
from revue_portee.collect import collection, enrichment, imports
from revue_portee.collect.collection import CollectorFactory
from revue_portee.collect.enrichment import WorkSource
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
from revue_portee.domain.framing import Framing
from revue_portee.domain.journal import verify_chain
from revue_portee.domain.protocol import FREE_TEXT_SECTIONS, ProtocolSection, ProtocolText
from revue_portee.domain.search import LANGUAGES, BlockRole, Database, WarningKind
from revue_portee.domain.sensitivity import LIMITS
from revue_portee.domain.suggestions import SuggestionKind, SuggestionOutcome
from revue_portee.i18n import EXPORT_LANGUAGES, translations
from revue_portee.i18n import gettext as _
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.protocol import criteria, framing, notes, qualification, registration, suggestions
from revue_portee.protocol.ai_assist import AITaskError, CostPreview, default_provider_factory
from revue_portee.protocol.document import protocol_document
from revue_portee.reporting.document import render_docx, render_markdown
from revue_portee.reporting.protocol import change_labels as report_change_labels
from revue_portee.reporting.protocol import checklist_status
from revue_portee.resources import peters_checklist
from revue_portee.search import runs, strategies
from revue_portee.search import suggestions as term_suggestions
from revue_portee.search.runs import DescriptorSource, default_descriptor_source
from revue_portee.sources import SourceError, SourceFactory, default_source_factory
from revue_portee.storage.project_folder import ProjectFolder, ProjectFolderError
from revue_portee.storage.repositories import projects
from revue_portee.storage.repositories import references as references_repo
from revue_portee.version import tool_version as current_tool_version
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
    jobs: BackgroundJobs | None = None,
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
        Database=Database,
        NEW_BLOCK=NEW_BLOCK,
        modification_types=MODIFICATION_TYPES,
        PccElement=PccElement,
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
