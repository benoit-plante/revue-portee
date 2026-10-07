"""Command-line entry point ``revue-portee``."""

import logging
from typing import Annotated

import typer

from revue_portee import __version__
from revue_portee.config.secrets import install_secret_redaction

app = typer.Typer(
    name="revue-portee",
    help="Revue de portée (JBI, PRISMA-ScR) avec l'IA comme second réviseur traçable.",
    no_args_is_help=False,
    add_completion=False,
)


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
            help="Afficher la version et quitter.",
        ),
    ] = False,
) -> None:
    """Revue de portée (JBI, PRISMA-ScR) avec l'IA comme second réviseur traçable."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s - %(message)s")
    install_secret_redaction()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
