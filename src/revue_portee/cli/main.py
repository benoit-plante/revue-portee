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
    ProjectFolder,
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
    "diagramme",
    help=_("Write the flow diagram of the screening (SVG, French and English) in the exports "
           "folder."),
)  # fmt: skip
def export_flow(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
) -> None:
    from revue_portee.i18n import EXPORT_LANGUAGES
    from revue_portee.screening.report import export_flow as write

    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    try:
        for language in EXPORT_LANGUAGES:
            path = write(folder, language=language, now=utc_now, tool_version=tool_version())
            typer.echo(_("Flow diagram written: {path}").format(path=path))
    finally:
        folder.close()


@app.command(
    "methode",
    help=_("Write the draft methods section on the AI in screening (Markdown and DOCX, French "
           "and English) in the exports folder."),
)  # fmt: skip
def export_methods(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
) -> None:
    from revue_portee.i18n import EXPORT_LANGUAGES
    from revue_portee.protocol.document import ExportFormat
    from revue_portee.screening.methods import export_methods as write

    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    try:
        for language in EXPORT_LANGUAGES:
            for export_format in ExportFormat:
                path = write(
                    folder,
                    language=language,
                    format=export_format,
                    now=utc_now,
                    tool_version=tool_version(),
                )
                typer.echo(_("Methods section written: {path}").format(path=path))
    finally:
        folder.close()


@app.command(
    "archive",
    help=_("Write the archive of the project (public by default) in the exports folder."),
)
def export_archive(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
    complete: Annotated[
        bool,
        typer.Option(
            "--complete",
            help=_(
                "Complete archive: also the database, the raw responses and the imported "
                "files (abstracts included: not for a public deposit)."
            ),
        ),
    ] = False,
) -> None:
    from revue_portee.screening.archive import ArchiveKind, SecretInArchiveError
    from revue_portee.screening.archive import export_archive as write

    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    kind = ArchiveKind.COMPLETE if complete else ArchiveKind.PUBLIC
    try:
        result = write(folder, kind=kind, now=utc_now, tool_version=tool_version())
    except SecretInArchiveError as error:
        raise _fail(str(error)) from error
    finally:
        folder.close()
    typer.echo(
        _("Archive written: {path} ({files} files, SHA-256 {digest})").format(
            path=result.path, files=result.files, digest=result.sha256
        )
    )
    if complete:
        typer.echo(
            _("This archive contains abstracts and raw responses: do not deposit it publicly.")
        )


@app.command(
    "retenues",
    help=_("Write the references kept for the full text (RIS and CSV) in the exports folder."),
)
def export_retained(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
) -> None:
    from revue_portee.screening.report import RetainedFormat
    from revue_portee.screening.report import export_retained as write

    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    try:
        for export_format in RetainedFormat:
            result = write(folder, format=export_format, now=utc_now, tool_version=tool_version())
            typer.echo(
                ngettext(
                    "{count} reference kept, written: {path}",
                    "{count} references kept, written: {path}",
                    result.count,
                ).format(count=result.count, path=result.path)
            )
    finally:
        folder.close()
    if result.provisional:
        typer.echo(_("The screening is not finished: this list may still change."), err=True)


@app.command(
    "donnees-extraites",
    help=_("Write the extracted values a person decided (CSV) in the exports folder."),
)
def export_extracted(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
) -> None:
    from revue_portee.extraction.validation import export_extraction

    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    try:
        path, written = export_extraction(folder)
    finally:
        folder.close()
    typer.echo(_("%(count)s values written to %(path)s.") % {"count": written, "path": path})


@app.command(
    "narratif",
    help=_(
        "Write the narrative synthesis revised by the person (Markdown and Word) in the "
        "exports folder; the AI's drafts not revised are never written."
    ),
)
def export_narrative(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
    langue: Annotated[str, typer.Option(help=_("Language of the exports (fr or en)."))] = "fr",
) -> None:
    from revue_portee.extraction.prefill import NoGridError
    from revue_portee.synthesis import narrative

    if langue not in ("fr", "en"):
        raise _fail(_("Unsupported language: {language} (fr or en).").format(language=langue))
    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    try:
        written = narrative.export_narrative(
            folder, language=langue, now=utc_now, tool_version=tool_version()
        )
    except NoGridError as error:
        raise _fail(str(error)) from error
    finally:
        folder.close()
    for path in written:
        typer.echo(str(path))


@app.command(
    "synthese",
    help=_(
        "Write the frequency tables (CSV, Markdown, XLSX) and, with two fields, the evidence "
        "map (SVG, HTML) in the exports folder."
    ),
)
def export_synthesis(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
    lignes: Annotated[str, typer.Option(help=_("Field of the rows of the map (D1…)."))] = "",
    colonnes: Annotated[str, typer.Option(help=_("Field of the columns of the map (D2…)."))] = "",
    seuil: Annotated[
        int, typer.Option(min=0, help=_("A cell is sparse with at most this many studies."))
    ] = 1,
    langue: Annotated[str, typer.Option(help=_("Language of the exports (fr or en)."))] = "fr",
) -> None:
    from revue_portee.extraction.prefill import NoGridError
    from revue_portee.synthesis import maps

    if bool(lignes) != bool(colonnes) or (lignes and lignes == colonnes):
        raise _fail(_("Give two different fields, one for the rows and one for the columns."))
    if langue not in ("fr", "en"):
        raise _fail(_("Unsupported language: {language} (fr or en).").format(language=langue))
    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    crossing = [(lignes, colonnes)] if lignes else []
    try:
        written = maps.export_tables(folder, language=langue, crosses=crossing, now=utc_now)
        for rows, columns in crossing:
            written += maps.export_map(
                folder, rows, columns, language=langue, sparse_max=seuil, now=utc_now,
                tool_version=tool_version(),
            )  # fmt: skip
    except (NoGridError, maps.UnknownFieldError) as error:
        raise _fail(str(error)) from error
    finally:
        folder.close()
    for path in written:
        typer.echo(str(path))


def _counts_line(folder: ProjectFolder) -> str:
    from revue_portee.fulltext.retrieval import retrieval_report
    from revue_portee.reporting.formats import percent

    counts = retrieval_report(folder).counts
    return _(
        "Full texts: {obtained} obtained of {sought} sought ({open_access} in open access, "
        "{share}; {uploaded} added by the team); not found: {not_found}; not retrievable: "
        "{not_retrievable}; never looked for: {not_sought}."
    ).format(
        obtained=counts.obtained,
        sought=counts.sought,
        open_access=counts.open_access,
        share=percent(counts.open_access_share or 0.0, "fr"),
        uploaded=counts.uploaded,
        not_found=counts.not_found,
        not_retrievable=counts.not_retrievable,
        not_sought=counts.not_sought,
    )


def _open_for_writing(dossier: Path) -> ProjectFolder:
    try:
        return open_project_folder(dossier, now=utc_now, tool_version=tool_version())
    except ProjectFolderError as error:
        raise _fail(str(error)) from error


@app.command(
    "textes-libres",
    help=_(
        "Look for the open access PDF of the references kept (OpenAlex, then Unpaywall) and "
        "store it in the project (calls these services)."
    ),
)
def open_access_texts(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
    limite: Annotated[
        int | None, typer.Option("--limite", help=_("Look for at most this many references."))
    ] = None,
    reessayer: Annotated[
        bool,
        typer.Option("--reessayer", help=_("Look again for the references not found before.")),
    ] = False,
) -> None:
    from revue_portee.config.secrets import MissingSecretError
    from revue_portee.fulltext.retrieval import retrieve_open_access
    from revue_portee.sources import OpenAccessSources, SourceError

    folder = _open_for_writing(dossier)
    try:
        summary = retrieve_open_access(
            folder,
            now=utc_now,
            tool_version=tool_version(),
            finder=OpenAccessSources,
            retry_not_found=reessayer,
            limit=limite,
            progress=lambda done, total: typer.echo(f"{done}/{total}", err=True),
        )
        typer.echo(
            _("References looked for: {looked_for}; texts obtained: {obtained}.").format(
                looked_for=summary.looked_for, obtained=summary.obtained
            )
        )
        typer.echo(_counts_line(folder))
    except (MissingSecretError, SourceError) as error:
        typer.echo(_counts_line(folder), err=True)
        raise _fail(str(error)) from error
    finally:
        folder.close()


@app.command(
    "textes-ajouter",
    help=_(
        "Add PDFs obtained by the team: each file is matched to its reference by DOI, then "
        "title, unless --reference is given."
    ),
)
def add_texts(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
    fichiers: Annotated[list[Path], typer.Argument(help=_("PDF files or folders of PDFs."))],
    reference: Annotated[
        str | None,
        typer.Option("--reference", help=_("Identifier of the reference (one file only).")),
    ] = None,
) -> None:
    from revue_portee.fulltext.page_benchmark import pdf_files
    from revue_portee.fulltext.retrieval import FulltextError, add_upload, upload_files

    try:
        paths = pdf_files(fichiers)
    except FileNotFoundError as error:
        raise _fail(str(error)) from error
    folder = _open_for_writing(dossier)
    try:
        if reference is not None:
            if len(paths) != 1:
                raise _fail(_("With --reference, give exactly one PDF file."))
            add_upload(
                folder, reference, paths[0].read_bytes(), filename=paths[0].name, now=utc_now,
                tool_version=tool_version(),
            )  # fmt: skip
            typer.echo(_("Text added: {file}").format(file=paths[0].name))
        else:
            report = upload_files(
                folder, ((p.name, p.read_bytes()) for p in paths), now=utc_now,
                tool_version=tool_version(),
            )  # fmt: skip
            for outcome in report.added:
                typer.echo(_("Added: {file} → {reference}").format(
                    file=outcome.filename, reference=outcome.reference_id))  # fmt: skip
            for outcome in report.already:
                typer.echo(_("Already in the project: {file}").format(file=outcome.filename))
            for outcome in report.unmatched:
                typer.echo(
                    _("No reference found (add it with --reference): {file}").format(
                        file=outcome.filename
                    ),
                    err=True,
                )
            for outcome in report.unreadable:
                typer.echo(f"{outcome.filename} : {outcome.message}", err=True)
        typer.echo(_counts_line(folder))
    except FulltextError as error:
        raise _fail(str(error)) from error
    finally:
        folder.close()


@app.command(
    "texte-introuvable",
    help=_("Declare that the full text of a reference cannot be obtained, with the reason."),
)
def text_not_retrievable(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
    reference: Annotated[str, typer.Argument(help=_("Identifier of the reference."))],
    raison: Annotated[str, typer.Option("--raison", help=_("Why the text cannot be obtained."))],
) -> None:
    from revue_portee.fulltext.retrieval import FulltextError, declare_not_retrievable

    folder = _open_for_writing(dossier)
    try:
        declare_not_retrievable(folder, reference, raison, now=utc_now, tool_version=tool_version())
        typer.echo(_counts_line(folder))
    except FulltextError as error:
        raise _fail(str(error)) from error
    finally:
        folder.close()


@app.command(
    "textes-manquants",
    help=_("Write the list of the references still without a full text (CSV) in the exports "
           "folder."),
)  # fmt: skip
def missing_texts(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
) -> None:
    from revue_portee.fulltext.retrieval import export_missing

    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    try:
        path, count = export_missing(folder)
        typer.echo(
            ngettext(
                "{count} reference without a full text, written: {path}",
                "{count} references without a full text, written: {path}",
                count,
            ).format(count=count, path=path)
        )
        typer.echo(_counts_line(folder))
    finally:
        folder.close()


@app.command(
    "textes-reconvertir",
    help=_(
        "Convert again the full texts converted by an older version of the tool (each new "
        "conversion is added; the old one stays)."
    ),
)
def reconvert_texts(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
) -> None:
    from revue_portee.fulltext.retrieval import reconvert

    folder = _open_for_writing(dossier)
    try:
        count = reconvert(folder, now=utc_now, tool_version=tool_version())
    finally:
        folder.close()
    typer.echo(_("Texts converted again: {count}").format(count=count))


@app.command(
    "jeu-etudes",
    help=_(
        "Build a set of PubMed records labelled by their ClinicalTrials.gov number, to test "
        "the grouping of reports of a same study (calls PubMed)."
    ),
)
def study_set(
    requete: Annotated[str, typer.Argument(help=_("PubMed query."))],
    sortie: Annotated[Path, typer.Option("--sortie", help=_("CSV file to write."))],
    limite: Annotated[int, typer.Option("--limite", help=_("Records read at most."))] = 3000,
) -> None:
    from revue_portee.collect import study_benchmark as bench
    from revue_portee.config.secrets import MissingSecretError, SecretName, get_secret
    from revue_portee.sources import SourceError
    from revue_portee.sources.http import make_client
    from revue_portee.sources.pubmed import PubMed

    try:
        pubmed = PubMed(make_client(), email=get_secret(SecretName.CONTACT_EMAIL), owns_client=True)
        try:
            records = bench.build_set(
                pubmed, requete, limit=limite, progress=lambda n: typer.echo(str(n), err=True)
            )
        finally:
            pubmed.close()
    except (MissingSecretError, SourceError) as error:
        raise _fail(str(error)) from error
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(bench.write_set(records), encoding="utf-8")
    typer.echo(
        _("Records with one trial number: {count}; written: {path}").format(
            count=len(records), path=sortie
        )
    )


@app.command(
    "banc-etudes",
    help=_(
        "Measure the rules that propose reports of a same study on a labelled set; local, no "
        "model call."
    ),
)
def study_benchmark(
    fichier: Annotated[Path, typer.Argument(help=_("CSV file built by jeu-etudes."))],
    role: Annotated[
        str, typer.Option("--role", help=_("Role of the set: development or test."))
    ] = "développement",
    auteurs: Annotated[int, typer.Option("--auteurs", help=_("Shared authors at least."))] = 2,
    mots: Annotated[
        float, typer.Option("--mots", help=_("Shared words at least (0 to 1)."))
    ] = 0.03,
    mots_un_auteur: Annotated[
        float,
        typer.Option("--mots-un-auteur", help=_("Shared words at least with one author (0 to 1).")),
    ] = 0.12,
    titre: Annotated[
        float, typer.Option("--titre", help=_("Title similarity at least (0 to 1)."))
    ] = 0.85,
    sortie: Annotated[Path, typer.Option("--sortie", help=_("Folder of the reports."))] = Path(
        "docs/resultats"
    ),
) -> None:
    from revue_portee.collect import study_benchmark as bench
    from revue_portee.dedup.reports import ReportLinkSettings

    if not fichier.is_file():
        raise _fail(_("File not found: {path}").format(path=fichier))
    settings = ReportLinkSettings(
        min_shared_authors=auteurs,
        min_text_overlap=mots,
        single_author_overlap=mots_un_auteur,
        min_title_similarity=titre,
    )
    name = fichier.stem
    test = bench.run_test(name, bench.read_set(fichier), now=utc_now(), settings=settings)
    sortie.mkdir(parents=True, exist_ok=True)
    report = sortie / f"etudes-{name}.md"
    report.write_text(bench.report_markdown(test, role=role), encoding="utf-8")
    e = test.evaluation
    typer.echo(
        _("{name}: recall {recall}, precision {precision}; report: {path}").format(
            name=name,
            recall="—" if e.recall is None else f"{e.recall:.3f}",
            precision="—" if e.precision is None else f"{e.precision:.3f}",
            path=report,
        )
    )


@app.command(
    "banc-extraction",
    help=_(
        "Measure the AI's pre-filling against an extraction made by hand (CSV); with "
        "--modele, write the file to fill instead; local, no model call."
    ),
)
def extraction_benchmark(
    dossier: Annotated[Path, typer.Argument(help=_("Project folder (.revue)."))],
    fichier: Annotated[Path, typer.Argument(help=_("CSV file: reference, field, value."))],
    modele: Annotated[
        bool, typer.Option("--modele", help=_("Write the file to fill for the included studies."))
    ] = False,
    sortie: Annotated[Path, typer.Option("--sortie", help=_("Folder of the reports."))] = Path(
        "docs/resultats"
    ),
) -> None:
    from revue_portee.extraction import benchmark as bench
    from revue_portee.extraction.prefill import extraction_state

    try:
        folder = open_project_folder(
            dossier, now=utc_now, tool_version=tool_version(), record_opening=False
        )
    except ProjectFolderError as error:
        raise _fail(str(error)) from error
    try:
        if modele:
            state = extraction_state(folder)
            if state.grid is None:
                raise _fail(_("Activate a version of the extraction grid first."))
            references = [s.primary.doi or s.primary.pmid or s.primary.id for s in state.studies]
            fichier.write_text(bench.write_template(state.grid, references), encoding="utf-8")
            typer.echo(_("File to fill written: {path}").format(path=fichier))
            return
        if not fichier.is_file():
            raise _fail(_("File not found: {path}").format(path=fichier))
        try:
            test = bench.run_test(folder, bench.read_reference(fichier), now=utc_now())
        except bench.NothingToCompareError as error:
            raise _fail(str(error)) from error
    finally:
        folder.close()
    sortie.mkdir(parents=True, exist_ok=True)
    report = sortie / f"extraction-{fichier.stem}.md"
    report.write_text(bench.report_markdown(test), encoding="utf-8")
    accuracy = test.agreed / test.compared if test.compared else 0.0
    typer.echo(
        _("Studies compared: {studies}; values in agreement: {accuracy}; report: {path}").format(
            studies=test.studies, accuracy=f"{accuracy:.1%}", path=report
        )
    )


@app.command(
    "banc-pages",
    help=_(
        "Compare the text extraction by page of PyMuPDF, pypdf and pdfplumber on test PDFs; "
        "local, no model call."
    ),
)
def page_benchmark(
    fichiers: Annotated[list[Path], typer.Argument(help=_("PDF files or folders of PDFs."))],
    graine: Annotated[int, typer.Option("--graine", help=_("Seed of the draw."))] = 2026,
    sortie: Annotated[Path, typer.Option("--sortie", help=_("Folder of the reports."))] = Path(
        "docs/resultats"
    ),
) -> None:
    from revue_portee.fulltext import page_benchmark as bench

    try:
        paths = bench.pdf_files(fichiers)
    except FileNotFoundError as error:
        raise _fail(str(error)) from error
    if not paths:
        raise _fail(_("No PDF file found."))
    result = bench.run_benchmark(paths, seed=graine, now=utc_now())
    sortie.mkdir(parents=True, exist_ok=True)
    report = sortie / "extraction-pages.md"
    report.write_text(bench.report_markdown(result), encoding="utf-8")
    for name in bench.EXTRACTORS:
        total = result.total(name)
        rate = "—" if total.rate is None else f"{total.rate:.1%}"
        typer.echo(
            _("{name}: right page for {rate} of {count} passages").format(
                name=name, rate=rate, count=total.checked
            )
        )
    typer.echo(_("Report: {path}").format(path=report))


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
    repetitions: Annotated[
        int,
        typer.Option(
            "--repetitions",
            min=1,
            max=5,
            help=_("Runs of the same records, to measure the response stability of the AI."),
        ),
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
            amount=cost.amount * repetitions,
        )
    )
    if repetitions > 1:
        typer.echo(
            _("{runs} runs of the same records (response stability).").format(runs=repetitions)
        )
    if not oui and not typer.confirm(_("Run the benchmark?")):
        raise typer.Exit(code=1)
    supervision = settings.supervision
    thresholds = Thresholds(
        exclude_below=float(supervision.exclude_below),
        include_above=float(supervision.include_above),
    )
    raw_path = brut or donnees.with_suffix(".brut.jsonl")
    results: list[benchmark.BenchmarkResult] = []
    for run in range(1, repetitions + 1):
        path = raw_path if repetitions == 1 else raw_path.with_suffix(f".{run}.jsonl")
        with path.open("w", encoding="utf-8") as raw_output:
            results.append(
                benchmark.run_benchmark(
                    name,
                    chosen,
                    chosen_criteria,
                    config=config,
                    provider=provider,
                    thresholds=thresholds,
                    ceiling=ceiling - sum((r.spent for r in results), Decimal(0)),
                    raw_output=raw_output,
                    now=utc_now,
                    seed=graine,
                    sampled=len(chosen) < len(records),
                    workers=paralleles,
                )
            )
        typer.echo(_("Raw answers: {path}").format(path=path))
    sortie.mkdir(parents=True, exist_ok=True)
    if repetitions == 1:
        report = sortie / f"banc-synergy-{name}.md"
        report.write_text(benchmark.report_markdown(results[0], chosen), encoding="utf-8")
    else:
        report = sortie / f"banc-stabilite-{name}.md"
        report.write_text(benchmark.report_stability(name, results, chosen), encoding="utf-8")
    typer.echo(_("Report written: {path}").format(path=report))


@app.command(
    "banc-doublons",
    help=_(
        "Measure the deduplication on held-out annotated sets (ASySD CSV files); local, "
        "no model call."
    ),
)
def dedup_benchmark(
    fichiers: Annotated[
        list[Path], typer.Argument(help=_("ASySD files *_duplicates_labelled.csv."))
    ],
    sortie: Annotated[Path, typer.Option("--sortie", help=_("Folder of the reports."))] = Path(
        "docs/resultats"
    ),
) -> None:
    from revue_portee.collect import dedup_benchmark as bench

    sortie.mkdir(parents=True, exist_ok=True)
    for path in fichiers:
        if not path.is_file():
            raise _fail(_("File not found: {path}").format(path=path))
        name = path.name.removesuffix(".csv").removesuffix("_duplicates_labelled")
        records = bench.read_asysd(path, created_at=utc_now())
        test = bench.run_test(name, records, now=utc_now())
        report = sortie / f"dedoublonnage-asysd-{name}.md"
        report.write_text(bench.report_markdown(test), encoding="utf-8")
        e = test.evaluation
        typer.echo(
            _("{name}: recall {recall}, precision {precision}; report: {path}").format(
                name=name, recall=f"{e.recall:.3f}", precision=f"{e.precision:.3f}", path=report
            )
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
