"""Runtime context and database session manager."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.paths import db_path, ensure_data_dir
from vizenlink_nvr.secrets.vault import (
    CanaryStatus,
    CredentialsUnreadable,
    Vault,
    initialise_vault,
    open_vault,
)
from vizenlink_nvr.timeutil import Clock, SystemClock

logger = logging.getLogger(__name__)


@dataclass
class Runtime:
    """Encapsulates application configuration, database connection, and clock."""

    settings: NvrSettings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    clock: Clock
    vault_status: CanaryStatus | None = None
    vault: Vault | None = None


@asynccontextmanager
async def open_runtime(
    settings: NvrSettings,
    clock: Clock | None = None,
) -> AsyncIterator[Runtime]:
    """Open NVR runtime with migrated SQLite database and secure permissions."""
    ensure_data_dir(settings)
    database_file = db_path(settings)
    upgrade_to_head(database_file)
    if os.name == "posix" and database_file.exists():
        os.chmod(database_file, 0o600)

    engine = create_engine_for(database_file)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    clk = clock if clock is not None else SystemClock()

    rt = Runtime(
        settings=settings,
        engine=engine,
        sessions=sessions,
        clock=clk,
    )
    try:
        rt.vault_status = await initialise_vault(rt)
        if rt.vault_status is not None and rt.vault_status.status == "ok":
            try:
                rt.vault = await open_vault(rt)
            except (CredentialsUnreadable, Exception) as exc:
                logger.debug("Vault open failed: %s", exc.__class__.__name__)
    except Exception as exc:
        logger.debug("Vault initialization deferred or failed: %s", exc)

    try:
        yield rt
    finally:
        await engine.dispose()
