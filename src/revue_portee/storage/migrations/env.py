"""Alembic environment: migrations run on a connection supplied by the application."""

from alembic import context

from revue_portee.storage.db import metadata

connection = context.config.attributes.get("connection")
if connection is None:  # pragma: no cover - only for `alembic` CLI use
    raise RuntimeError("Run migrations through revue_portee.storage.migrate.upgrade().")

context.configure(
    connection=connection,
    target_metadata=metadata,
    render_as_batch=True,  # SQLite cannot ALTER most constraints in place
)
with context.begin_transaction():
    context.run_migrations()
