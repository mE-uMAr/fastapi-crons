"""
SQLAlchemy lock backends for fastapi-crons.

Two implementations sharing the same LockBackend interface:

- SQLAlchemyLockBackend     : table-based, works with SQLite / PostgreSQL / MySQL
- PostgreSQLAdvisoryLockBackend : advisory locks, PostgreSQL only, zero table

Install with: pip install fastapi-crons[sqlalchemy]

Usage:
    from sqlalchemy.ext.asyncio import create_async_engine
    from fastapi_crons.locking.sqlalchemy import SQLAlchemyLockBackend
    from fastapi_crons.locking import DistributedLockManager
    from fastapi_crons import CronConfig

    engine  = create_async_engine("postgresql+asyncpg://...")
    backend = SQLAlchemyLockBackend(engine)
    manager = DistributedLockManager(backend, CronConfig())

Alembic integration:
    from fastapi_crons.locking.sqlalchemy import cron_locks_metadata
    target_metadata = [Base.metadata, cron_locks_metadata]
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi_crons.locking import LockBackend

logger = logging.getLogger("fastapi_cron.locking.sqlalchemy")


try:
    from sqlalchemy import MetaData, String, delete, select, update
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
except ImportError as err:
    raise ImportError(
        "SQLAlchemy is required for SQLAlchemyLockBackend.\n"
        "Install with: pip install fastapi-crons[sqlalchemy]"
    ) from err


class _LockBase(DeclarativeBase):
    pass


class _CronLock(_LockBase):
    """Distributed lock record with explicit TTL."""

    __tablename__ = "cron_locks"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    lock_id: Mapped[str] = mapped_column(String(36), nullable=False)
    acquired_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    acquired_at: Mapped[str] = mapped_column(String(50), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(50), nullable=False, index=True)


cron_locks_metadata: MetaData = _LockBase.metadata
"""
SQLAlchemy MetaData containing the cron_locks table.

    from fastapi_crons.locking.sqlalchemy import cron_locks_metadata
    target_metadata = [Base.metadata, cron_locks_metadata]
"""


def _upsert_lock(dialect_name: str, values: dict[str, Any], set_cols: dict[str, Any]) -> Any:
    if dialect_name in ("mysql", "mariadb"):
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        return mysql_insert(_CronLock).values(**values).on_duplicate_key_update(**set_cols)

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as insert
    elif dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as insert  # type: ignore[assignment]
    else:
        raise NotImplementedError(
            f"Unsupported dialect: {dialect_name!r}. Supported: postgresql, sqlite, mysql, mariadb."
        )

    return (
        insert(_CronLock)
        .values(**values)
        .on_conflict_do_update(index_elements=["key"], set_=set_cols)
    )


class SQLAlchemyLockBackend(LockBackend):
    """
    Table-based distributed lock backend for fastapi-crons.

    Uses a cron_locks table with explicit expires_at TTL.
    Compatible with SQLite, PostgreSQL, and MySQL.

    Expired locks are cleaned up passively on each acquire attempt —
    no background task required.

    Args:
        engine       : SQLAlchemy Engine or AsyncEngine.
        create_tables: Auto-create cron_locks table (default True).
                       Set to False when using Alembic.
        instance_id  : Optional identifier stored in acquired_by column.
    """

    def __init__(
        self,
        engine: Any,
        create_tables: bool = True,
        instance_id: str | None = None,
    ) -> None:
        from sqlalchemy.ext.asyncio import AsyncEngine

        self._is_async: bool = isinstance(engine, AsyncEngine)
        self._engine = engine
        self._dialect: str = engine.dialect.name
        self._create_tables = create_tables
        self._instance_id = instance_id
        self._tables_created = False
        self._init_lock = asyncio.Lock()

    async def _ensure_tables(self) -> None:
        if not self._create_tables or self._tables_created:
            return
        async with self._init_lock:
            if self._tables_created:
                return
            await self._run(None, create_all=True)
            self._tables_created = True

    async def _run(self, stmt: Any, *, create_all: bool = False) -> Any:
        if self._is_async:
            async with self._engine.begin() as conn:
                if create_all:
                    await conn.run_sync(_LockBase.metadata.create_all)
                    return None
                return await conn.execute(stmt)
        else:

            def _blocking() -> Any:
                with self._engine.begin() as _conn:
                    if create_all:
                        _LockBase.metadata.create_all(_conn)
                        return None
                    return _conn.execute(stmt)

            return await asyncio.to_thread(_blocking)

    async def acquire_lock(self, key: str, ttl: int) -> str | None:
        """
        Acquire a lock.

        Passively cleans expired locks on each attempt.
        Returns a lock_id string if acquired, None if already locked.
        """
        await self._ensure_tables()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        await self._run(delete(_CronLock).where(_CronLock.expires_at <= now_iso))

        result = await self._run(
            select(_CronLock.lock_id, _CronLock.expires_at).where(_CronLock.key == key)
        )
        row = result.fetchone()
        if row:
            return None

        lock_id = str(uuid.uuid4())
        expires_at = (now + timedelta(seconds=ttl)).isoformat()
        values = {
            "key": key,
            "lock_id": lock_id,
            "acquired_by": self._instance_id,
            "acquired_at": now_iso,
            "expires_at": expires_at,
        }
        set_cols = {k: v for k, v in values.items() if k != "key"}

        try:
            await self._run(_upsert_lock(self._dialect, values, set_cols))
            return lock_id
        except Exception as e:
            logger.debug("Lock acquisition race for %s: %s", key, e)
            return None

    async def release_lock(self, key: str, lock_id: str) -> bool:
        """Release a lock only if we own it (lock_id matches)."""
        await self._ensure_tables()
        result = await self._run(
            delete(_CronLock).where((_CronLock.key == key) & (_CronLock.lock_id == lock_id))
        )
        return result.rowcount > 0  # type: ignore

    async def is_locked(self, key: str) -> bool:
        """Check if a key is currently locked (not expired)."""
        await self._ensure_tables()
        now_iso = datetime.now(timezone.utc).isoformat()
        result = await self._run(
            select(_CronLock.key).where((_CronLock.key == key) & (_CronLock.expires_at > now_iso))
        )
        return result.fetchone() is not None

    async def renew_lock(self, key: str, lock_id: str, ttl: int) -> bool:
        """Extend the TTL of an owned lock."""
        await self._ensure_tables()
        new_expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
        result = await self._run(
            update(_CronLock)
            .where((_CronLock.key == key) & (_CronLock.lock_id == lock_id))
            .values(expires_at=new_expires)
        )
        return result.rowcount > 0  # type: ignore

    async def dispose(self) -> None:
        """Dispose the engine connection pool."""
        if self._is_async:
            await self._engine.dispose()
        else:
            await asyncio.to_thread(self._engine.dispose)


class PostgreSQLAdvisoryLockBackend(LockBackend):
    """
    PostgreSQL advisory lock backend for fastapi-crons.

    Uses pg_try_advisory_lock() / pg_advisory_unlock() — no table required.
    Advisory locks are session-scoped and released automatically on disconnect.

    Lighter than table-based locks but PostgreSQL-only.
    TTL and renew are no-ops (advisory locks don't expire natively) —
    the DistributedLockManager renewal loop is harmless but unnecessary.

    Args:
        engine: AsyncEngine or Engine pointing to a PostgreSQL database.
    """

    def __init__(self, engine: Any) -> None:
        from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

        if not isinstance(engine, AsyncEngine):
            raise TypeError(
                "PostgreSQLAdvisoryLockBackend requires an AsyncEngine. "
                "Use create_async_engine() with asyncpg."
            )
        self._engine = engine
        self._connections: dict[str, tuple[AsyncConnection, str]] = {}
        self._conn_lock = asyncio.Lock()

    def _key_to_int(self, key: str) -> int:
        """
        Convert a string key to a 64-bit integer for pg_advisory_lock.

        Uses hash() truncated to PostgreSQL's bigint range.
        Collision probability is negligible for typical cron job counts.
        """
        return hash(key) & 0x7FFFFFFFFFFFFFFF

    async def acquire_lock(self, key: str, ttl: int) -> str | None:
        """
        Try to acquire a PostgreSQL advisory lock.

        Uses pg_try_advisory_lock (non-blocking).
        TTL is ignored — advisory locks are session-scoped.
        """
        lock_key = self._key_to_int(key)

        async with self._conn_lock:
            if key in self._connections:
                return None

            conn = await self._engine.connect()
            from sqlalchemy import text

            result = await conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
            )
            acquired = result.scalar()

            if acquired:
                lock_id = str(uuid.uuid4())
                self._connections[key] = (conn, lock_id)
                logger.debug("Advisory lock acquired for %s (pg_key=%d)", key, lock_key)
                return lock_id
            else:
                await conn.close()
                return None

    async def release_lock(self, key: str, lock_id: str) -> bool:
        """Release an advisory lock and close its connection."""
        async with self._conn_lock:
            entry = self._connections.get(key)
            if not entry:
                return False

            conn, stored_lock_id = entry
            if stored_lock_id != lock_id:
                return False

            lock_key = self._key_to_int(key)
            from sqlalchemy import text

            try:
                await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
                await conn.close()
            except Exception as e:
                logger.warning("Error releasing advisory lock for %s: %s", key, e)
            finally:
                del self._connections[key]

            return True

    async def is_locked(self, key: str) -> bool:
        """
        Check if the advisory lock is held by any session.

        Queries pg_locks system view.
        """
        lock_key = self._key_to_int(key)
        async with self._engine.connect() as conn:
            from sqlalchemy import text

            result = await conn.execute(
                text(
                    "SELECT 1 FROM pg_locks "
                    "WHERE locktype = 'advisory' "
                    "AND classid = (:key >> 32)::int "
                    "AND objid = (:key & x'ffffffff'::bigint)::int "
                    "AND granted = true"
                ),
                {"key": lock_key},
            )
            return result.fetchone() is not None

    async def renew_lock(self, key: str, lock_id: str, ttl: int) -> bool:
        """
        No-op — advisory locks don't expire natively.

        Returns True if we still hold the lock (connection alive).
        """
        async with self._conn_lock:
            entry = self._connections.get(key)
            if not entry:
                return False
            _, stored_lock_id = entry
            return stored_lock_id == lock_id
