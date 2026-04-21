from collections.abc import AsyncIterator
import os

from sqlalchemy import MetaData
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


settings = get_settings()
_engine = None
_session_factory = None
_engine_pid: int | None = None


def _is_asyncpg_url(database_url: str) -> bool:
    return make_url(database_url).drivername == "postgresql+asyncpg"


def _uses_supabase_pooler(url: URL) -> bool:
    return bool(url.host and url.host.endswith(".pooler.supabase.com"))


def _should_disable_prepared_statements(database_url: str) -> bool:
    if settings.database_disable_prepared_statements is not None:
        return settings.database_disable_prepared_statements

    url = make_url(database_url)
    return _is_asyncpg_url(database_url) and _uses_supabase_pooler(url)


def _build_engine_kwargs(database_url: str) -> dict[str, object]:
    engine_kwargs: dict[str, object] = {"pool_pre_ping": True}

    if _should_disable_prepared_statements(database_url):
        # Supabase transaction poolers run behind PgBouncer and reject asyncpg
        # prepared statements unless statement caching is disabled.
        engine_kwargs["connect_args"] = {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }

    return engine_kwargs


def get_engine():
    global _engine, _session_factory, _engine_pid

    current_pid = os.getpid()
    if _engine is None or _session_factory is None or _engine_pid != current_pid:
        _engine = create_async_engine(
            settings.database_url,
            **_build_engine_kwargs(settings.database_url),
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)
        _engine_pid = current_pid

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


async def init_database() -> None:
    if not settings.database_auto_create:
        return

    import app.models.notification  # noqa: F401

    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def dispose_database() -> None:
    global _engine, _session_factory, _engine_pid

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
    _engine_pid = None
