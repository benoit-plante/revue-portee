from typer.testing import CliRunner

from revue_portee import __version__
from revue_portee.cli.main import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"revue-portee {__version__}"


def test_no_arguments_shows_french_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Afficher la version et quitter." in result.output
