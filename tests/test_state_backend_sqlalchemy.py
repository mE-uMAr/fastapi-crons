"""Tests for SQLAlchemy state backend — sync and async engines."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def sa_sync_engine(temp_db):
    """Sync SQLite in-memory engine."""
    sqlalchemy = pytest.importorskip("sqlalchemy", reason="pip install fastapi-crons[sqlalchemy]")
    engine = sqlalchemy.create_engine(
        f"sqlite:///{temp_db}",
    )
    yield engine
    engine.dispose()


@pytest.fixture
async def sa_async_engine(temp_db):
    """Async SQLite in-memory engine (requires aiosqlite)."""
    sqlalchemy = pytest.importorskip(
        "sqlalchemy.ext.asyncio", reason="pip install fastapi-crons[sqlalchemy]"
    )
    engine = sqlalchemy.create_async_engine(
        f"sqlite+aiosqlite:///{temp_db}",
    )
    yield engine
    await engine.dispose()


@pytest.fixture
def sqlalchemy_backend_sync(sa_sync_engine):
    """SQLAlchemyStateBackend wrapping a sync engine."""
    from fastapi_crons.state.sqlalchemy import SQLAlchemyStateBackend

    return SQLAlchemyStateBackend(sa_sync_engine, create_tables=True)


@pytest.fixture
async def sqlalchemy_backend_async(sa_async_engine):
    """SQLAlchemyStateBackend wrapping an async engine."""
    from fastapi_crons.state.sqlalchemy import SQLAlchemyStateBackend

    return SQLAlchemyStateBackend(sa_async_engine, create_tables=True)


class TestSQLAlchemyStateBackendAsync:
    """
    Mirror of TestSQLiteStateBackend using an async SQLAlchemy engine.
    Ensures SQLAlchemyStateBackend is a drop-in replacement.
    """

    @pytest.mark.asyncio
    async def test_set_and_get_last_run(self, sqlalchemy_backend_async):
        now = _now()
        await sqlalchemy_backend_async.set_last_run("job_a", now)
        result = await sqlalchemy_backend_async.get_last_run("job_a")
        assert result == now.isoformat()

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_last_run(self, sqlalchemy_backend_async):
        result = await sqlalchemy_backend_async.get_last_run("ghost_job")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_last_run(self, sqlalchemy_backend_async):
        first = _now()
        second = first + timedelta(minutes=5)

        await sqlalchemy_backend_async.set_last_run("job_a", first)
        await sqlalchemy_backend_async.set_last_run("job_a", second)

        result = await sqlalchemy_backend_async.get_last_run("job_a")
        assert result == second.isoformat()

    @pytest.mark.asyncio
    async def test_get_all_jobs(self, sqlalchemy_backend_async):
        now = _now()
        await sqlalchemy_backend_async.set_last_run("job_a", now)
        await sqlalchemy_backend_async.set_last_run("job_b", now + timedelta(minutes=1))

        jobs = await sqlalchemy_backend_async.get_all_jobs()
        names = [j[0] for j in jobs]

        assert "job_a" in names
        assert "job_b" in names
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_set_job_status_running(self, sqlalchemy_backend_async):
        await sqlalchemy_backend_async.set_job_status("job_a", "running", "inst-1")
        status = await sqlalchemy_backend_async.get_job_status("job_a")

        assert status is not None
        assert status["status"] == "running"
        assert status["instance_id"] == "inst-1"
        assert status["started_at"] is not None

    @pytest.mark.asyncio
    async def test_update_job_status(self, sqlalchemy_backend_async):
        await sqlalchemy_backend_async.set_job_status("job_a", "running", "inst-1")
        await sqlalchemy_backend_async.set_job_status("job_a", "completed", "inst-1")

        status = await sqlalchemy_backend_async.get_job_status("job_a")
        assert status["status"] == "completed"

    @pytest.mark.asyncio
    async def test_started_at_preserved_on_completion(self, sqlalchemy_backend_async):
        """
        started_at must remain unchanged after running -> completed/failed.
        This is the specific behavior of our partial upsert.
        """
        await sqlalchemy_backend_async.set_job_status("job_a", "running", "inst-1")
        status_running = await sqlalchemy_backend_async.get_job_status("job_a")
        started_at_original = status_running["started_at"]

        await sqlalchemy_backend_async.set_job_status("job_a", "completed", "inst-1")
        status_completed = await sqlalchemy_backend_async.get_job_status("job_a")

        assert status_completed["started_at"] == started_at_original

    @pytest.mark.asyncio
    async def test_started_at_preserved_on_failure(self, sqlalchemy_backend_async):
        await sqlalchemy_backend_async.set_job_status("job_a", "running", "inst-1")
        status_running = await sqlalchemy_backend_async.get_job_status("job_a")
        started_at_original = status_running["started_at"]

        await sqlalchemy_backend_async.set_job_status("job_a", "failed", "inst-1")
        status_failed = await sqlalchemy_backend_async.get_job_status("job_a")

        assert status_failed["started_at"] == started_at_original

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_status(self, sqlalchemy_backend_async):
        status = await sqlalchemy_backend_async.get_job_status("ghost_job")
        assert status is None

    @pytest.mark.asyncio
    async def test_log_job_execution_completed(self, sqlalchemy_backend_async):
        start = _now()
        end = start + timedelta(seconds=5)
        await sqlalchemy_backend_async.log_job_execution(
            "job_a", "inst-1", "completed", start, end, 5.0
        )

    @pytest.mark.asyncio
    async def test_log_job_execution_with_error(self, sqlalchemy_backend_async):
        start = _now()
        end = start + timedelta(seconds=2)
        await sqlalchemy_backend_async.log_job_execution(
            "job_a", "inst-1", "failed", start, end, 2.0, "Something exploded"
        )

    @pytest.mark.asyncio
    async def test_log_job_execution_no_completed_at(self, sqlalchemy_backend_async):
        """completed_at and duration are optional."""
        await sqlalchemy_backend_async.log_job_execution("job_a", "inst-1", "failed", _now())

    @pytest.mark.asyncio
    async def test_tables_created_once(self, sqlalchemy_backend_async):
        """_ensure_tables must execute only once despite concurrent calls."""
        await asyncio.gather(
            sqlalchemy_backend_async.set_last_run("job_a", _now()),
            sqlalchemy_backend_async.set_last_run("job_b", _now()),
            sqlalchemy_backend_async.set_last_run("job_c", _now()),
        )
        assert sqlalchemy_backend_async._tables_created is True

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, sqlalchemy_backend_async):
        """10 concurrent writes must not raise an exception."""
        await asyncio.gather(
            *[sqlalchemy_backend_async.set_last_run(f"job_{i}", _now()) for i in range(10)]
        )
        jobs = await sqlalchemy_backend_async.get_all_jobs()
        assert len(jobs) == 10

    @pytest.mark.asyncio
    async def test_engine_detection_async(self, sqlalchemy_backend_async):
        assert sqlalchemy_backend_async._is_async is True
        assert sqlalchemy_backend_async._dialect == "sqlite"


class TestSQLAlchemyStateBackendSync:
    """
    Same suite as the async version but with a synchronous Engine.
    Validates that the asyncio.to_thread path works correctly.
    """

    @pytest.mark.asyncio
    async def test_set_and_get_last_run(self, sqlalchemy_backend_sync):
        now = _now()
        await sqlalchemy_backend_sync.set_last_run("job_a", now)
        result = await sqlalchemy_backend_sync.get_last_run("job_a")
        assert result == now.isoformat()

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_last_run(self, sqlalchemy_backend_sync):
        result = await sqlalchemy_backend_sync.get_last_run("ghost_job")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_last_run(self, sqlalchemy_backend_sync):
        first = _now()
        second = first + timedelta(minutes=5)

        await sqlalchemy_backend_sync.set_last_run("job_a", first)
        await sqlalchemy_backend_sync.set_last_run("job_a", second)

        result = await sqlalchemy_backend_sync.get_last_run("job_a")
        assert result == second.isoformat()

    @pytest.mark.asyncio
    async def test_get_all_jobs(self, sqlalchemy_backend_sync):
        now = _now()
        await sqlalchemy_backend_sync.set_last_run("job_a", now)
        await sqlalchemy_backend_sync.set_last_run("job_b", now + timedelta(minutes=1))

        jobs = await sqlalchemy_backend_sync.get_all_jobs()
        names = [j[0] for j in jobs]

        assert "job_a" in names
        assert "job_b" in names
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_set_job_status_running(self, sqlalchemy_backend_sync):
        await sqlalchemy_backend_sync.set_job_status("job_a", "running", "inst-1")
        status = await sqlalchemy_backend_sync.get_job_status("job_a")

        assert status is not None
        assert status["status"] == "running"
        assert status["instance_id"] == "inst-1"
        assert status["started_at"] is not None

    @pytest.mark.asyncio
    async def test_update_job_status(self, sqlalchemy_backend_sync):
        await sqlalchemy_backend_sync.set_job_status("job_a", "running", "inst-1")
        await sqlalchemy_backend_sync.set_job_status("job_a", "completed", "inst-1")

        status = await sqlalchemy_backend_sync.get_job_status("job_a")
        assert status["status"] == "completed"

    @pytest.mark.asyncio
    async def test_started_at_preserved_on_completion(self, sqlalchemy_backend_sync):
        await sqlalchemy_backend_sync.set_job_status("job_a", "running", "inst-1")
        started_at_original = (await sqlalchemy_backend_sync.get_job_status("job_a"))["started_at"]

        await sqlalchemy_backend_sync.set_job_status("job_a", "completed", "inst-1")
        status = await sqlalchemy_backend_sync.get_job_status("job_a")

        assert status["started_at"] == started_at_original

    @pytest.mark.asyncio
    async def test_started_at_preserved_on_failure(self, sqlalchemy_backend_sync):
        await sqlalchemy_backend_sync.set_job_status("job_a", "running", "inst-1")
        started_at_original = (await sqlalchemy_backend_sync.get_job_status("job_a"))["started_at"]

        await sqlalchemy_backend_sync.set_job_status("job_a", "failed", "inst-1")
        status = await sqlalchemy_backend_sync.get_job_status("job_a")

        assert status["started_at"] == started_at_original

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_status(self, sqlalchemy_backend_sync):
        status = await sqlalchemy_backend_sync.get_job_status("ghost_job")
        assert status is None

    @pytest.mark.asyncio
    async def test_log_job_execution_completed(self, sqlalchemy_backend_sync):
        start = _now()
        end = start + timedelta(seconds=5)
        await sqlalchemy_backend_sync.log_job_execution(
            "job_a", "inst-1", "completed", start, end, 5.0
        )

    @pytest.mark.asyncio
    async def test_log_job_execution_with_error(self, sqlalchemy_backend_sync):
        start = _now()
        end = start + timedelta(seconds=2)
        await sqlalchemy_backend_sync.log_job_execution(
            "job_a", "inst-1", "failed", start, end, 2.0, "Something exploded"
        )

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, sqlalchemy_backend_sync):
        """
        For the sync backend, calls are serialized via asyncio.to_thread.
        We verify that there is no race condition on _ensure_tables.
        """
        await asyncio.gather(
            *[sqlalchemy_backend_sync.set_last_run(f"job_{i}", _now()) for i in range(10)]
        )
        jobs = await sqlalchemy_backend_sync.get_all_jobs()
        assert len(jobs) == 10

    @pytest.mark.asyncio
    async def test_engine_detection_sync(self, sqlalchemy_backend_sync):
        assert sqlalchemy_backend_sync._is_async is False
        assert sqlalchemy_backend_sync._dialect == "sqlite"


class TestSQLAlchemyStateBackendNoAutoCreate:
    """
    Verifies that create_tables=False does not create tables automatically.
    The dev is responsible for creating them via Alembic.
    """

    @pytest.mark.asyncio
    async def test_no_auto_create_raises_on_missing_table(self, sa_async_engine):
        from sqlalchemy.exc import OperationalError

        from fastapi_crons.state.sqlalchemy import SQLAlchemyStateBackend

        backend = SQLAlchemyStateBackend(sa_async_engine, create_tables=False)

        with pytest.raises(OperationalError):
            await backend.set_last_run("job_a", _now())

    @pytest.mark.asyncio
    async def test_no_auto_create_works_after_manual_create(self, sa_async_engine):
        from fastapi_crons.state.sqlalchemy import SQLAlchemyStateBackend, cron_metadata

        async with sa_async_engine.begin() as conn:
            await conn.run_sync(cron_metadata.create_all)

        backend = SQLAlchemyStateBackend(sa_async_engine, create_tables=False)
        now = _now()
        await backend.set_last_run("job_a", now)
        result = await backend.get_last_run("job_a")
        assert result == now.isoformat()


class TestSQLModelStateBackendAlias:
    """SQLModelStateBackend is a pure alias — same class, same behavior."""

    def test_alias_is_same_class(self):
        cron_sqlalchemy = pytest.importorskip(
            "fastapi_crons.state.sqlalchemy", reason="pip install fastapi-crons[sqlalchemy]"
        )
        assert cron_sqlalchemy.SQLModelStateBackend is cron_sqlalchemy.SQLAlchemyStateBackend

    @pytest.mark.asyncio
    async def test_alias_functional(self, sa_async_engine):
        from fastapi_crons.state.sqlalchemy import SQLModelStateBackend

        backend = SQLModelStateBackend(sa_async_engine, create_tables=True)
        now = _now()
        await backend.set_last_run("job_a", now)
        assert await backend.get_last_run("job_a") == now.isoformat()
