"""Database engine creation, URLs, and Alembic migration helpers."""

import importlib.resources
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def sync_url(path: Path) -> str:
    """Return synchronous SQLite URL for Alembic migrations and inspections."""
    posix_path = path.resolve().as_posix()
    return f"sqlite:///{posix_path}"


def async_url(path: Path) -> str:
    """Return asynchronous aiosqlite URL for SQLAlchemy AsyncEngine."""
    posix_path = path.resolve().as_posix()
    return f"sqlite+aiosqlite:///{posix_path}"


def create_engine_for(path: Path) -> AsyncEngine:
    """Create an AsyncEngine for SQLite with WAL mode, foreign keys, and normal sync."""
    engine = create_async_engine(async_url(path))

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


def alembic_config(path: Path) -> Config:
    """Build programmatic Alembic Config for the given database file."""
    migrations_dir = str(importlib.resources.files("vizenlink_nvr.db").joinpath("migrations"))
    cfg = Config()
    cfg.set_main_option("script_location", migrations_dir)
    cfg.attributes["sqlalchemy.url"] = sync_url(path)
    return cfg


def upgrade_to_head(path: Path) -> None:
    """Programmatically upgrade SQLite database to head revision."""
    cfg = alembic_config(path)
    command.upgrade(cfg, "head")


def current_revision(path: Path) -> str | None:
    """Get the current Alembic revision in the SQLite database, or None if empty/missing."""
    if not path.exists():
        return None
    engine = sa.create_engine(sync_url(path))
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        return context.get_current_revision()


def head_revision() -> str:
    """Get the latest revision ID defined in migrations."""
    migrations_dir = str(importlib.resources.files("vizenlink_nvr.db").joinpath("migrations"))
    cfg = Config()
    cfg.set_main_option("script_location", migrations_dir)
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    return head or ""
