"""Apply Alembic migrations to a project database."""

from importlib.resources import files

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from revue_portee.storage.db import write_transaction

__all__ = ["current_revision", "head_revision", "upgrade"]


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(files("revue_portee.storage") / "migrations"))
    return config


def head_revision() -> str:
    head = ScriptDirectory.from_config(_config()).get_current_head()
    if head is None:  # pragma: no cover - there is always at least one migration
        raise RuntimeError("no migration found")
    return head


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def upgrade(engine: Engine) -> None:
    """Bring the database to the latest schema."""
    config = _config()
    with write_transaction(engine) as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
