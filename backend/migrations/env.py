"""Use the application's connection and metadata without loading secrets into config files."""
from __future__ import annotations
from alembic import context
from app.db import Base
from app import models  # noqa: F401

connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
with context.begin_transaction():
    context.run_migrations()
