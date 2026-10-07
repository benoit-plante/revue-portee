"""Local web application (FastAPI + Jinja2 + HTMX), French interface.

The server only answers on 127.0.0.1 (ENF-SEC-06). Because any web page open in the
browser could still send requests to it, every form carries a per-process token and
requests with a foreign ``Host`` or ``Origin`` are refused (CSRF, DNS rebinding).
"""

import secrets
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from revue_portee.clock import utc_now
from revue_portee.domain.criteria import (
    CriteriaVersion,
    CriterionKind,
    EmptyCriteriaError,
    MissingRationaleError,
    PccElement,
    VersionStatus,
    diff_versions,
)
from revue_portee.domain.framing import Framing
from revue_portee.i18n import gettext as _
from revue_portee.i18n import translations
from revue_portee.protocol import criteria, framing, notes
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import projects
from revue_portee.version import tool_version as current_tool_version

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


def create_app(
    folder: ProjectFolder,
    *,
    now: Callable[[], datetime] = utc_now,
    tool_version: str | None = None,
) -> FastAPI:
    """Application serving one open project folder."""
    context = AppContext(
        folder=folder,
        now=now,
        tool_version=tool_version or current_tool_version(),
        csrf_token=secrets.token_urlsafe(32),
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
        PccElement=PccElement,
        CriterionKind=CriterionKind,
    )

    def render(
        request: Request, name: str, values: Mapping[str, Any], *, status_code: int = 200
    ) -> HTMLResponse:
        with folder.engine.connect() as connection:
            project = projects.get_project(connection)
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
        request: Request, *, error: str | None = None, saved: bool = False, status_code: int = 200
    ) -> HTMLResponse:
        return render(
            request,
            "cadrage.html",
            {
                "current": framing.current_framing(folder),
                "history": framing.framing_history(folder),
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

    # --- Criteria ---------------------------------------------------------------------

    def criteria_page(
        request: Request, *, error: str | None = None, status_code: int = 200
    ) -> HTMLResponse:
        state = criteria.criteria_state(folder)
        draft_diff = None
        if state.draft is not None and state.active is not None:
            draft_diff = diff_versions(state.active, state.draft)
        return render(
            request,
            "criteres.html",
            {"state": state, "draft_diff": draft_diff, "error": error},
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

    def draft_or_404() -> CriteriaVersion:
        draft = criteria.criteria_state(folder).draft
        if draft is None:
            raise HTTPException(status_code=404, detail=_("There is no draft of the criteria."))
        return draft

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

    @app.post("/criteres/activer")
    def activate(
        request: Request, _csrf: Csrf, justification: Annotated[str, Form()] = ""
    ) -> Response:
        draft_or_404()
        try:
            activated = criteria.activate_draft(
                folder, rationale=justification, now=now, tool_version=context.tool_version
            )
        except MissingRationaleError:
            return criteria_page(
                request,
                error=_("A rationale is required to create a new version of the criteria."),
                status_code=422,
            )
        except EmptyCriteriaError:
            return criteria_page(
                request, error=_("Add at least one criterion before activating."), status_code=422
            )
        return see_other(f"/criteres/versions/{activated.number}")

    @app.post("/criteres/abandonner")
    def discard(_csrf: Csrf) -> RedirectResponse:
        draft_or_404()
        criteria.discard_draft(folder, now=now, tool_version=context.tool_version)
        return see_other("/criteres")

    @app.get("/criteres/versions/{number}", response_class=HTMLResponse)
    def show_version(request: Request, number: int) -> HTMLResponse:
        try:
            found = criteria.version(folder, number)
        except criteria.UnknownVersionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if found.status is VersionStatus.DRAFT:
            return see_other("/criteres#brouillon")  # type: ignore[return-value]
        return render(request, "version.html", {"version": found})

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
                "check": notes.verify_journal(folder),
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
