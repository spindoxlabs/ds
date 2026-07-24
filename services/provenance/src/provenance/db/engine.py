import logging
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ..config import get_settings

log = logging.getLogger(__name__)

_SERVICE = "ds-provenance"
_UPGRADE_HINT = "task db:migrate:provenance"

_engine = None
_session_factory = None


class Base(DeclarativeBase):
    pass


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False
        )
    return _session_factory


async def verify_schema() -> None:
    """Refuse to start against a database alembic did not own.

    Alembic is the only thing that writes schema. Startup verifies rather than
    repairs, because a half-built schema is worse than a missing one: tables
    look present, the recorded revision stays stale, and the failure surfaces
    later as a 500 on whichever read touched the column that never arrived.

    Set ``DB_SKIP_SCHEMA_CHECK=true`` to bypass — for a test harness that builds
    its own schema, never for a deployment.
    """
    if os.getenv("DB_SKIP_SCHEMA_CHECK", "").lower() in ("1", "true", "yes"):
        log.warning("DB_SKIP_SCHEMA_CHECK is set — not verifying the schema revision")
        return

    head = _migration_head()
    try:
        async with get_engine().connect() as conn:
            current = await conn.scalar(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError as exc:
        raise RuntimeError(
            f"{_SERVICE}: cannot read the schema revision ({exc.__class__.__name__}). "
            f"If this is a fresh database, create it and run: {_UPGRADE_HINT}"
        ) from exc

    if current is None:
        raise RuntimeError(
            f"{_SERVICE}: the database has no alembic revision. Run: {_UPGRADE_HINT}"
        )
    if current != head:
        raise RuntimeError(
            f"{_SERVICE}: database is at schema revision {current!r} but this build "
            f"expects {head!r}. Run: {_UPGRADE_HINT}"
        )
    log.info("%s: schema revision %s", _SERVICE, current)


def _migration_head() -> str:
    """The single head revision of this service's migration tree."""
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            f"{_SERVICE}: expected exactly one migration head, found {heads}"
        )
    return heads[0]
