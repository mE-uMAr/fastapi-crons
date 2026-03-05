"""Tests for SQLAlchemy lock backends — SQLAlchemyLockBackend."""

import asyncio
from datetime import datetime, timezone

import pytest


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
async def sa_async_engine_lock():
    pytest.importorskip("sqlalchemy", reason="pip install fastapi-crons[sqlalchemy]")
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    yield engine
    await engine.dispose()


@pytest.fixture
async def sa_async_engine_fresh():
    """Dedicated fresh engine for no-auto-create tests."""
    pytest.importorskip("sqlalchemy", reason="pip install fastapi-crons[sqlalchemy]")
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    yield engine
    await engine.dispose()


@pytest.fixture
def sa_sync_engine_lock(tmp_path):
    pytest.importorskip("sqlalchemy", reason="pip install fastapi-crons[sqlalchemy]")
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'test_locks.db'}")
    yield engine
    engine.dispose()


@pytest.fixture
def sa_sync_engine_fresh(tmp_path):
    """Dedicated fresh engine for no-auto-create tests."""
    pytest.importorskip("sqlalchemy", reason="pip install fastapi-crons[sqlalchemy]")
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'test_locks_fresh.db'}")
    yield engine
    engine.dispose()


@pytest.fixture
async def lock_backend_async(sa_async_engine_lock):
    from fastapi_crons.locking.sqlalchemy import SQLAlchemyLockBackend

    return SQLAlchemyLockBackend(sa_async_engine_lock, create_tables=True)


@pytest.fixture
def lock_backend_sync(sa_sync_engine_lock):
    from fastapi_crons.locking.sqlalchemy import SQLAlchemyLockBackend

    return SQLAlchemyLockBackend(sa_sync_engine_lock, create_tables=True)


class TestSQLAlchemyLockBackendAsync:
    @pytest.mark.asyncio
    async def test_acquire_returns_lock_id(self, lock_backend_async):
        lock_id = await lock_backend_async.acquire_lock("job:test", ttl=60)
        assert lock_id is not None
        assert len(lock_id) == 36

    @pytest.mark.asyncio
    async def test_acquire_same_key_twice_fails(self, lock_backend_async):
        await lock_backend_async.acquire_lock("job:test", ttl=60)
        second = await lock_backend_async.acquire_lock("job:test", ttl=60)
        assert second is None

    @pytest.mark.asyncio
    async def test_acquire_different_keys(self, lock_backend_async):
        id1 = await lock_backend_async.acquire_lock("job:a", ttl=60)
        id2 = await lock_backend_async.acquire_lock("job:b", ttl=60)
        assert id1 is not None
        assert id2 is not None
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_is_locked_true_after_acquire(self, lock_backend_async):
        await lock_backend_async.acquire_lock("job:test", ttl=60)
        assert await lock_backend_async.is_locked("job:test") is True

    @pytest.mark.asyncio
    async def test_is_locked_false_before_acquire(self, lock_backend_async):
        assert await lock_backend_async.is_locked("job:test") is False

    @pytest.mark.asyncio
    async def test_release_owned_lock(self, lock_backend_async):
        lock_id = await lock_backend_async.acquire_lock("job:test", ttl=60)
        result = await lock_backend_async.release_lock("job:test", lock_id)
        assert result is True
        assert await lock_backend_async.is_locked("job:test") is False

    @pytest.mark.asyncio
    async def test_release_wrong_lock_id(self, lock_backend_async):
        await lock_backend_async.acquire_lock("job:test", ttl=60)
        result = await lock_backend_async.release_lock("job:test", "wrong-id")
        assert result is False
        assert await lock_backend_async.is_locked("job:test") is True

    @pytest.mark.asyncio
    async def test_release_nonexistent_lock(self, lock_backend_async):
        result = await lock_backend_async.release_lock("job:ghost", "any-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_reacquire_after_release(self, lock_backend_async):
        lock_id = await lock_backend_async.acquire_lock("job:test", ttl=60)
        await lock_backend_async.release_lock("job:test", lock_id)
        new_id = await lock_backend_async.acquire_lock("job:test", ttl=60)
        assert new_id is not None

    @pytest.mark.asyncio
    async def test_renew_owned_lock(self, lock_backend_async):
        lock_id = await lock_backend_async.acquire_lock("job:test", ttl=60)
        result = await lock_backend_async.renew_lock("job:test", lock_id, ttl=120)
        assert result is True

    @pytest.mark.asyncio
    async def test_renew_wrong_lock_id(self, lock_backend_async):
        await lock_backend_async.acquire_lock("job:test", ttl=60)
        result = await lock_backend_async.renew_lock("job:test", "wrong-id", ttl=120)
        assert result is False

    @pytest.mark.asyncio
    async def test_renew_nonexistent_lock(self, lock_backend_async):
        result = await lock_backend_async.renew_lock("job:ghost", "any-id", ttl=60)
        assert result is False

    @pytest.mark.asyncio
    async def test_expired_lock_can_be_reacquired(self, lock_backend_async):
        """Expired locks are cleaned up passively on next acquire."""
        lock_id = await lock_backend_async.acquire_lock("job:test", ttl=1)
        assert lock_id is not None

        from sqlalchemy import update

        from fastapi_crons.locking.sqlalchemy import _CronLock

        past = "2000-01-01T00:00:00+00:00"
        async with lock_backend_async._engine.begin() as conn:
            await conn.execute(
                update(_CronLock).where(_CronLock.key == "job:test").values(expires_at=past)
            )

        new_id = await lock_backend_async.acquire_lock("job:test", ttl=60)
        assert new_id is not None

    @pytest.mark.asyncio
    async def test_tables_created_once(self, lock_backend_async):
        await asyncio.gather(
            lock_backend_async.acquire_lock("job:a", ttl=60),
            lock_backend_async.acquire_lock("job:b", ttl=60),
        )
        assert lock_backend_async._tables_created is True


class TestSQLAlchemyLockBackendSync:
    @pytest.mark.asyncio
    async def test_acquire_returns_lock_id(self, lock_backend_sync):
        lock_id = await lock_backend_sync.acquire_lock("job:test", ttl=60)
        assert lock_id is not None

    @pytest.mark.asyncio
    async def test_acquire_same_key_twice_fails(self, lock_backend_sync):
        await lock_backend_sync.acquire_lock("job:test", ttl=60)
        second = await lock_backend_sync.acquire_lock("job:test", ttl=60)
        assert second is None

    @pytest.mark.asyncio
    async def test_is_locked_after_acquire(self, lock_backend_sync):
        await lock_backend_sync.acquire_lock("job:test", ttl=60)
        assert await lock_backend_sync.is_locked("job:test") is True

    @pytest.mark.asyncio
    async def test_release_owned_lock(self, lock_backend_sync):
        lock_id = await lock_backend_sync.acquire_lock("job:test", ttl=60)
        assert await lock_backend_sync.release_lock("job:test", lock_id) is True
        assert await lock_backend_sync.is_locked("job:test") is False

    @pytest.mark.asyncio
    async def test_renew_owned_lock(self, lock_backend_sync):
        lock_id = await lock_backend_sync.acquire_lock("job:test", ttl=60)
        assert await lock_backend_sync.renew_lock("job:test", lock_id, ttl=120) is True


class TestSQLAlchemyLockBackendNoAutoCreate:
    @pytest.mark.asyncio
    async def test_no_auto_create_raises_on_missing_table(self, sa_async_engine_fresh):
        from sqlalchemy.exc import OperationalError

        from fastapi_crons.locking.sqlalchemy import SQLAlchemyLockBackend

        backend = SQLAlchemyLockBackend(sa_async_engine_fresh, create_tables=False)
        with pytest.raises(OperationalError):
            await backend.acquire_lock("job:test", ttl=60)

    @pytest.mark.asyncio
    async def test_no_auto_create_works_after_manual_create(self, sa_async_engine_fresh):
        from fastapi_crons.locking.sqlalchemy import SQLAlchemyLockBackend, cron_locks_metadata

        async with sa_async_engine_fresh.begin() as conn:
            await conn.run_sync(cron_locks_metadata.create_all)

        backend = SQLAlchemyLockBackend(sa_async_engine_fresh, create_tables=False)
        lock_id = await backend.acquire_lock("job:test", ttl=60)
        assert lock_id is not None

    @pytest.mark.asyncio
    async def test_no_auto_create_sync_raises(self, sa_sync_engine_fresh):
        from fastapi_crons.locking.sqlalchemy import SQLAlchemyLockBackend

        backend = SQLAlchemyLockBackend(sa_sync_engine_fresh, create_tables=False)
        from sqlalchemy.exc import OperationalError

        with pytest.raises(OperationalError):
            await backend.acquire_lock("job:test", ttl=60)
