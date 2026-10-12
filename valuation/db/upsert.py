"""Dialect-aware INSERT helpers for idempotent upserts."""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session


def dialect_insert(db: Session, model):
    """Return an insert() object compatible with the current DB dialect."""
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        return sqlite_insert(model)
    return pg_insert(model)
