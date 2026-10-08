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


@app.command("protocole", help=_("Write the protocol (Markdown and DOCX) in the exports folder."))
def export_protocol(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
    langue: Annotated[
        str, typer.Option("--langue", help=_("Language of the protocol: fr or en."))
    ] = "fr",
) -> None:
    from revue_portee.i18n import EXPORT_LANGUAGES
    from revue_portee.protocol.document import ExportFormat
    from revue_portee.protocol.document import export_protocol as write

    if langue not in EXPORT_LANGUAGES:
        raise _fail(_("Unsupported language: {language} (fr or en).").format(language=langue))
    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    try:
        for export_format in ExportFormat:
            path = write(
                folder,
                language=langue,
                format=export_format,
                now=utc_now,
                tool_version=tool_version(),
            )
            typer.echo(_("Protocol written: {path}").format(path=path))
    finally:
        folder.close()


@app.command(
    "banc-synergy",
    help=_("Measure the AI screener on a labelled SYNERGY dataset (calls the model)."),
)
def synergy_benchmark(
    donnees: Annotated[Path, typer.Argument(help=_("CSV file: title, abstract, label_included."))],
    criteres: Annotated[Path, typer.Option("--criteres", help=_("YAML file of the criteria."))],
    plafond: Annotated[str, typer.Option("--plafond", help=_("Ceiling of the run in US dollars."))],
    nom: Annotated[str, typer.Option("--nom", help=_("Name of the dataset."))] = "",
    echantillon: Annotated[
        int | None,
        typer.Option(
            "--echantillon",
            help=_("Records to screen: every inclusion, the rest drawn among exclusions."),
        ),
    ] = None,
    graine: Annotated[int, typer.Option("--graine", help=_("Seed of the draw."))] = 2026,
    sortie: Annotated[
        Path, typer.Option("--sortie", help=_("Folder of the Markdown report."))
    ] = Path("docs/resultats"),
    brut: Annotated[
        Path | None,
        typer.Option(
            "--brut", help=_("JSON Lines file of the raw answers (outside the repository).")
        ),
    ] = None,
    oui: Annotated[bool, typer.Option("--oui", help=_("Do not ask to confirm the cost."))] = False,
    paralleles: Annotated[
        int, typer.Option("--paralleles", min=1, max=16, help=_("Model calls made at a time."))
    ] = 1,
) -> None:
    from decimal import Decimal, InvalidOperation

    from revue_portee.ai.costs import UnknownPriceError
    from revue_portee.ai.providers import UnknownProviderError
    from revue_portee.ai.settings import TaskNotAvailableError
    from revue_portee.ai.tasks.screening import SCREEN_REFERENCE
    from revue_portee.config.secrets import MissingSecretError
    from revue_portee.domain.screening import Thresholds
    from revue_portee.protocol import ai_assist
    from revue_portee.resources import default_ai_settings
    from revue_portee.screening import benchmark

    try:
        ceiling = Decimal(plafond.replace(",", "."))
    except InvalidOperation as error:
        raise _fail(_("The ceiling must be a positive amount.")) from error
    if not ceiling.is_finite() or ceiling <= 0:
        raise _fail(_("The ceiling must be a positive amount."))
    name = nom or donnees.stem
    try:
        records = benchmark.read_dataset(donnees)
        chosen_criteria = benchmark.read_criteria(criteres)
        settings = default_ai_settings()
        config = settings.enabled_task(SCREEN_REFERENCE.name)
        provider = ai_assist.default_provider_factory(config)
        chosen = benchmark.select_records(records, echantillon, graine)
        cost = benchmark.estimate(provider, benchmark.to_inputs(chosen, chosen_criteria))
    except (
        benchmark.BenchmarkError,
        TaskNotAvailableError,
        UnknownPriceError,
        UnknownProviderError,
        MissingSecretError,
    ) as error:
        raise _fail(str(error)) from error
    typer.echo(
        _(
            "{count} records ({included} included) with {provider} — {model}: at most {amount} USD."
        ).format(
            count=len(chosen),
            included=sum(r.included for r in chosen),
            provider=provider.name,
            model=config.model,
            amount=cost.amount,
        )
    )
    if not oui and not typer.confirm(_("Run the benchmark?")):
        raise typer.Exit(code=1)
    supervision = settings.supervision
    thresholds = Thresholds(
        exclude_below=float(supervision.exclude_below),
        include_above=float(supervision.include_above),
    )
    raw_path = brut or donnees.with_suffix(".brut.jsonl")
    with raw_path.open("w", encoding="utf-8") as raw_output:
        result = benchmark.run_benchmark(
            name,
            chosen,
            chosen_criteria,
            config=config,
            provider=provider,
            thresholds=thresholds,
            ceiling=ceiling,
            raw_output=raw_output,
            now=utc_now,
            seed=graine,
            sampled=len(chosen) < len(records),
            workers=paralleles,
        )
    sortie.mkdir(parents=True, exist_ok=True)
    report = sortie / f"banc-synergy-{name}.md"
    report.write_text(benchmark.report_markdown(result, chosen), encoding="utf-8")
    typer.echo(_("Report written: {path}").format(path=report))
    typer.echo(_("Raw answers: {path}").format(path=raw_path))


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
