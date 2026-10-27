"""Alembic environment configuration."""

import logging
from logging.config import fileConfig
from typing import Any, Literal

import sqlalchemy as sa
from alembic import context

from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.engine import sync_url
from vizenlink_nvr.db.models import Base
from vizenlink_nvr.db.types import UtcDateTime
from vizenlink_nvr.paths import db_path

logger = logging.getLogger("alembic.env")
config = context.config

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception as exc:
        logger.debug("Could not configure logging: %s", exc)

target_metadata = Base.metadata


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | Literal[False]:
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.BigInteger()"
    return False


def get_url() -> str:
    url = config.attributes.get("sqlalchemy.url")
    if url:
        return str(url)
    settings = load_settings()
    return sync_url(db_path(settings))


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_url()
    connectable = sa.create_engine(url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            render_item=render_item,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
