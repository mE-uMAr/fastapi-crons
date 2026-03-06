"""
SQLAlchemy state backend for fastapi-crons.

Supports both sync and async SQLAlchemy engines.
Install with: pip install fastapi-crons[sqlalchemy]

Usage:
    # Async engine (recommended for FastAPI)
    from sqlalchemy.ext.asyncio import create_async_engine
    from fastapi_crons.state.sqlalchemy import SQLAlchemyStateBackend

    engine = create_async_engine("postgresql+asyncpg://user:pass@host/db")
    backend = SQLAlchemyStateBackend(engine)

    # Sync engine
    from sqlalchemy import create_engine
    engine = create_engine("postgresql://user:pass@host/db")
    backend = SQLAlchemyStateBackend(engine)

Alembic integration (env.py):
    from fastapi_crons.state.sqlalchemy import cron_metadata
    target_metadata = [Base.metadata, cron_metadata]
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from fastapi_crons.state import StateBackend

logger = logging.getLogger("fastapi_cron.state.sqlalchemy")

try:
    from sqlalchemy import Float, Insert, Integer, MetaData, String, Text, select
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
except ImportError as e:
    raise ImportError(
        "SQLAlchemy is required for SQLAlchemyStateBackend.\n"
        "Install with: pip install fastapi-crons[sqlalchemy]"
    ) from e


if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine


class _CronBase(DeclarativeBase):
    """Private declarative base for fastapi-crons tables."""


class _JobState(_CronBase):
    """Tracks the last run timestamp per job."""

    __tablename__ = "cron_job_state"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_run: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


class _JobStatus(_CronBase):
    """Tracks the current execution status per job."""

    __tablename__ = "cron_job_status"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


class _JobExecutionLog(_CronBase):
    """Append-only execution history."""

    __tablename__ = "cron_job_execution_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


cron_metadata: MetaData = _CronBase.metadata
"""
SQLAlchemy MetaData containing all fastapi-crons tables.

Use in your Alembic env.py to merge cron tables into your migration flow:

    from fastapi_crons.state.sqlalchemy import cron_metadata
    target_metadata = [Base.metadata, cron_metadata]
"""


def _upsert(
    table: type, dialect_name: str, values: dict[str, Any], set_cols: dict[str, Any]
) -> Insert:
    """
    Build a dialect-native upsert statement.

    - PostgreSQL : INSERT ... ON CONFLICT DO UPDATE SET ...
    - SQLite     : INSERT ... ON CONFLICT DO UPDATE SET ...
    - MySQL/Maria: INSERT ... ON DUPLICATE KEY UPDATE ...
    """
    if dialect_name in ("mysql", "mariadb"):
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        return mysql_insert(table).values(**values).on_duplicate_key_update(**set_cols)

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as insert
    elif dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as insert  # type: ignore[assignment]
    else:
        raise NotImplementedError(
            f"Unsupported dialect: {dialect_name!r}. Supported: postgresql, sqlite, mysql, mariadb."
        )

    return (
        insert(table).values(**values).on_conflict_do_update(index_elements=["name"], set_=set_cols)
    )


class SQLAlchemyStateBackend(StateBackend):
    """
    SQLAlchemy-based state backend for fastapi-crons.

    Accepts both sync (Engine) and async (AsyncEngine) SQLAlchemy engines.
    The backend detects the engine type at initialization and dispatches
    database operations accordingly.

    Args:
        engine: A SQLAlchemy Engine or AsyncEngine instance.

    Example:
        # Async (recommended for FastAPI)
        engine = create_async_engine("postgresql+asyncpg://...")
        backend = SQLAlchemyStateBackend(engine)

        # Sync
        engine = create_engine("postgresql://...")
        backend = SQLAlchemyStateBackend(engine)

        # Pass to Crons
        crons = Crons(app, state_backend=backend)
    """

    def __init__(self, engine: Engine | AsyncEngine, create_tables: bool = True) -> None:
        try:
            from sqlalchemy.ext.asyncio import AsyncEngine

            self._is_async: bool = isinstance(engine, AsyncEngine)
        except ImportError:
            self._is_async = False

        self._engine = engine
        self._dialect: str = engine.dialect.name
        self._create_tables = create_tables
        self._tables_created: bool = False
        self._init_lock: asyncio.Lock = asyncio.Lock()

        logger.debug(
            "SQLAlchemyStateBackend initialized — dialect=%s async=%s",
            self._dialect,
            self._is_async,
        )

    async def _ensure_tables(self) -> None:
        """Create tables if they don't exist — guarded by asyncio.Lock."""
        if not self._create_tables or self._tables_created:
            return
        async with self._init_lock:
            if self._tables_created:
                return
            await self._run(None, create_all=True)
            self._tables_created = True

    async def _run(self, stmt: Any, *, create_all: bool = False) -> Any:
        """
        Execute a Core statement against the engine.

        AsyncEngine  → native async execution
        Engine (sync) → asyncio.to_thread to avoid blocking the event loop
        """
        if self._is_async:
            async with self._engine.begin() as conn:  # type: ignore
                if create_all:
                    await conn.run_sync(_CronBase.metadata.create_all)
                    return None
                return await conn.execute(stmt)
        else:

            def _blocking() -> Any:
                with self._engine.begin() as _conn:  # type: ignore
                    if create_all:
                        _CronBase.metadata.create_all(_conn)
                        return None
                    return _conn.execute(stmt)

            return await asyncio.to_thread(_blocking)

    async def set_last_run(self, job_name: str, timestamp: datetime) -> None:
        """Upsert the last run timestamp for a job."""
        await self._ensure_tables()
        now = datetime.now(timezone.utc).isoformat()
        values = {"name": job_name, "last_run": timestamp.isoformat(), "updated_at": now}
        stmt = _upsert(
            _JobState, self._dialect, values, {k: v for k, v in values.items() if k != "name"}
        )
        await self._run(stmt)

    async def get_last_run(self, job_name: str) -> str | None:
        """Get the last run timestamp for a job."""
        await self._ensure_tables()
        result = await self._run(select(_JobState.last_run).where(_JobState.name == job_name))
        row = result.fetchone()
        return row[0] if row else None

    async def get_all_jobs(self) -> list[tuple[str, str | None]]:
        """Get all jobs and their last run timestamps, ordered by name."""
        await self._ensure_tables()
        result = await self._run(
            select(_JobState.name, _JobState.last_run).order_by(_JobState.name)
        )
        return list(result.fetchall())

    async def set_job_status(self, job_name: str, status: str, instance_id: str) -> None:
        """
        Upsert the status of a job.

        On INSERT  : all columns including started_at are written.
        On UPDATE  : started_at is preserved when transitioning to
                     completed/failed (only status, instance_id, updated_at change).
        """
        await self._ensure_tables()
        now = datetime.now(timezone.utc).isoformat()

        if status == "running":
            values: dict[str, Any] = {
                "name": job_name,
                "status": status,
                "instance_id": instance_id,
                "started_at": now,
                "updated_at": now,
            }
            set_cols = {k: v for k, v in values.items() if k != "name"}
        else:
            values = {
                "name": job_name,
                "status": status,
                "instance_id": instance_id,
                "started_at": None,
                "updated_at": now,
            }
            set_cols = {"status": status, "instance_id": instance_id, "updated_at": now}

        stmt = _upsert(_JobStatus, self._dialect, values, set_cols)
        await self._run(stmt)

    async def get_job_status(self, job_name: str) -> dict[str, Any] | None:
        """Get the current status dict for a job."""
        await self._ensure_tables()
        result = await self._run(
            select(
                _JobStatus.status,
                _JobStatus.instance_id,
                _JobStatus.started_at,
                _JobStatus.updated_at,
            ).where(_JobStatus.name == job_name)
        )
        row = result.fetchone()
        if row:
            return {
                "status": row[0],
                "instance_id": row[1],
                "started_at": row[2],
                "updated_at": row[3],
            }
        return None

    async def log_job_execution(
        self,
        job_name: str,
        instance_id: str,
        status: str,
        started_at: datetime,
        completed_at: datetime | None = None,
        duration: float | None = None,
        error_message: str | None = None,
    ) -> None:
        """Append an execution record to the log table (pure INSERT, no upsert)."""
        await self._ensure_tables()
        from sqlalchemy import insert as sa_insert

        stmt = sa_insert(_JobExecutionLog).values(
            job_name=job_name,
            instance_id=instance_id,
            status=status,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat() if completed_at else None,
            duration=duration,
            error_message=error_message,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await self._run(stmt)

    async def dispose(self) -> None:
        """Dispose the engine connection pool gracefully."""
        if self._is_async:
            await cast(AsyncEngine, self._engine).dispose()
        else:
            await asyncio.to_thread(self._engine.dispose)


SQLModelStateBackend = SQLAlchemyStateBackend
"""
Alias of SQLAlchemyStateBackend for projects using SQLModel.

SQLModel engines are fully SQLAlchemy-compatible — no separate
implementation is needed. This alias exists purely for discoverability.

Usage:
    from sqlmodel import create_engine
    from fastapi_crons.state.sqlalchemy import SQLModelStateBackend

    engine = create_engine("postgresql://...")
    backend = SQLModelStateBackend(engine)
"""
