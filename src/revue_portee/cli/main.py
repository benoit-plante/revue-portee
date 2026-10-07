"""Command-line entry point ``revue-portee`` (French interface)."""

import logging
from pathlib import Path
from typing import Annotated

import typer

from revue_portee import __version__
from revue_portee.clock import utc_now
from revue_portee.config.secrets import install_secret_redaction
from revue_portee.i18n import gettext as _
from revue_portee.i18n import ngettext
from revue_portee.storage.project_folder import (
    ProjectFolderError,
    create_project_folder,
    open_project_folder,
)
from revue_portee.version import tool_version

app = typer.Typer(
    name="revue-portee",
    help=_("Scoping review (JBI, PRISMA-ScR) with AI as a traceable second reviewer."),
    no_args_is_help=False,
    add_completion=False,
)

LOCAL_HOST = "127.0.0.1"  # ENF-SEC-06: the server never listens on other interfaces


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"revue-portee {__version__}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help=_("Show the version and exit."),
        ),
    ] = False,
) -> None:
    """Revue de portée (JBI, PRISMA-ScR) avec l'IA comme second réviseur traçable."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s - %(message)s")
    install_secret_redaction()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def _fail(message: str) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=1)


@app.command("nouveau", help=_("Create a review project folder (.revue)."))
def new_project(
    dossier: Annotated[Path, typer.Argument(help=_("Folder to create (.revue is added)."))],
    titre: Annotated[str, typer.Option("--titre", help=_("Title of the review."))],
    reviseur: Annotated[str, typer.Option("--reviseur", help=_("Name of the human reviewer."))],
    langue: Annotated[str, typer.Option("--langue", help=_("Main language (ISO code)."))] = "fr",
    description: Annotated[str, typer.Option("--description", help=_("Short description."))] = "",
) -> None:
    try:
        folder = create_project_folder(
            dossier,
            title=titre,
            language=langue,
            reviewer_name=reviseur,
            description=description,
            now=utc_now,
            tool_version=tool_version(),
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    folder.close()
    typer.echo(_("Project created: {folder}").format(folder=folder.path))


@app.command("verifier-journal", help=_("Check the hash chain of the project journal."))
def check_journal(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
) -> None:
    from revue_portee.protocol.notes import verify_journal

    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    try:
        check = verify_journal(folder)
    finally:
        folder.close()
    if not check.valid:
        position = (check.first_invalid_index or 0) + 1
        raise _fail(
            _("Journal altered: the hash chain breaks at entry {position}.").format(
                position=position
            )
        )
    typer.echo(
        ngettext(
            "Journal intact: {count} entry, hash chain verified.",
            "Journal intact: {count} entries, hash chain verified.",
            check.checked,
        ).format(count=check.checked)
    )


@app.command("serve", help=_("Open the web interface of a project on 127.0.0.1."))
def serve(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
    port: Annotated[int, typer.Option("--port", help=_("Local port."))] = 8000,
) -> None:  # pragma: no cover - starts a blocking server; the app itself is tested
    import uvicorn

    from revue_portee.web.app import create_app

    try:
        folder = open_project_folder(dossier, now=utc_now, tool_version=tool_version())
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    typer.echo(
        _("Open http://{host}:{port}/ in your browser (Ctrl+C to stop).").format(
            host=LOCAL_HOST, port=port
        )
    )
    try:
        uvicorn.run(create_app(folder), host=LOCAL_HOST, port=port, log_level="warning")
    finally:
        folder.close()
