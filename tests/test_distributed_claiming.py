"""Tests for multi-worker coordination, retry accounting and schedule drift.

Covers the behaviour reported in issue #28: every worker registers the same
jobs, and a job that becomes due must execute exactly once across the fleet.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from fastapi_crons.config import CronConfig
from fastapi_crons.job import CronJob
from fastapi_crons.locking import (
    DEFAULT_LOCK_KEY_PREFIX,
    DistributedLockManager,
    LocalLockBackend,
    RedisLockBackend,
)
from fastapi_crons.runner import run_job_loop
from fastapi_crons.state import SQLiteStateBackend


class RecordingRedis:
    """Minimal stand-in that records the keys a backend touches."""

    def __init__(self):
        self.keys: list[str] = []
        self.store: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None):
        self.keys.append(key)
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def exists(self, key):
        self.keys.append(key)
        return key in self.store

    async def eval(self, script, numkeys, key, *args):
        self.keys.append(key)
        return 1


class TestTickClaiming:
    """A scheduled tick is claimed by exactly one worker."""

    async def test_same_tick_claimed_once(self):
        shared = LocalLockBackend()
        config = CronConfig()
        managers = [DistributedLockManager(shared, config) for _ in range(5)]

        key = "job:report:tick:2026-01-01T00:00:00+00:00"
        results = await asyncio.gather(*(m.claim(key) for m in managers))

        assert sum(results) == 1, "exactly one worker may claim a tick"

    async def test_claim_is_not_released_after_use(self):
        """The fence must outlive the run, or a late worker redoes the work."""
        shared = LocalLockBackend()
        config = CronConfig()
        manager = DistributedLockManager(shared, config)
        key = "job:report:tick:2026-01-01T00:00:00+00:00"

        assert await manager.claim(key) is True
        # A claim is never tracked for release/renewal, unlike acquire_lock.
        assert key not in manager.active_locks
        await manager.cleanup()

        latecomer = DistributedLockManager(shared, config)
        assert await latecomer.claim(key) is False

    async def test_distinct_ticks_are_independent(self):
        shared = LocalLockBackend()
        manager = DistributedLockManager(shared, CronConfig())

        assert await manager.claim("job:x:tick:2026-01-01T00:00:00+00:00") is True
        assert await manager.claim("job:x:tick:2026-01-01T00:00:01+00:00") is True


class TestFleetExecution:
    """End-to-end: several workers running the same job loop."""

    @pytest.mark.parametrize("workers", [2, 5])
    async def test_job_runs_once_per_tick_across_workers(self, workers, temp_db):
        runs: list[datetime] = []

        async def job_body():
            runs.append(datetime.now(timezone.utc))

        shared = LocalLockBackend()  # one shared lock store, as Redis would be
        states, tasks = [], []
        for i in range(workers):
            config = CronConfig()
            config.sqlite_db_path = temp_db
            config.instance_id = f"w{i}"
            state = SQLiteStateBackend(temp_db)
            states.append(state)
            manager = DistributedLockManager(shared, config)
            job = CronJob(job_body, "* * * * * *", name="fleet_job")  # every second
            tasks.append(asyncio.create_task(run_job_loop(job, state, manager, config)))

        await asyncio.sleep(2.5)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for state in states:
            await state.close()

        ticks = {run.replace(microsecond=0) for run in runs}
        assert runs, "the job should have run at least once"
        assert len(runs) == len(ticks), (
            f"{len(runs)} executions for {len(ticks)} ticks: a tick ran on more than one worker"
        )


class TestRetryAccounting:
    """A job that succeeds on its final attempt has succeeded."""

    async def test_success_on_final_retry_is_not_reported_as_failure(self, temp_db):
        attempts = {"n": 0}

        async def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("boom")
            return "ok"

        config = CronConfig()
        config.sqlite_db_path = temp_db
        state = SQLiteStateBackend(temp_db)
        manager = DistributedLockManager(LocalLockBackend(), config)

        job = CronJob(flaky, "* * * * * *", name="flaky", max_retries=2, retry_delay=0.01)
        job.next_run = datetime.now(timezone.utc)

        errors, successes = [], []
        job.add_on_error_hook(lambda name, ctx: errors.append(ctx))
        job.add_after_run_hook(lambda name, ctx: successes.append(ctx))

        task = asyncio.create_task(run_job_loop(job, state, manager, config))
        await asyncio.sleep(0.8)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        status = await state.get_job_status("flaky")
        await state.close()

        assert successes, "after_run hooks should fire on success"
        assert errors == [], "on_error hooks must not fire for a job that succeeded"
        assert status["status"] == "completed"


class TestScheduleCoalescing:
    """A job slower than its interval must not drift behind the schedule."""

    def test_update_next_run_skips_elapsed_ticks(self):
        job = CronJob(lambda: None, "* * * * * *", name="slow")
        now = datetime.now(timezone.utc)

        job.update_next_run(now + timedelta(seconds=5))

        assert job.next_run > now + timedelta(seconds=5)

    def test_update_next_run_without_argument_advances_one_tick(self):
        job = CronJob(lambda: None, "* * * * * *", name="plain")
        first = job.next_run

        job.update_next_run()

        assert job.next_run == first + timedelta(seconds=1)


class TestLockKeyNamespacing:
    """Lock keys are namespaced and configurable (shared Redis instances)."""

    async def test_keys_use_the_default_namespace(self):
        client = RecordingRedis()
        backend = RedisLockBackend(client)

        await backend.acquire_lock("job:report", 30)

        assert client.keys == [f"{DEFAULT_LOCK_KEY_PREFIX}job:report"]
        assert not client.keys[0].startswith("lock:")

    async def test_prefix_is_configurable(self):
        client = RecordingRedis()
        backend = RedisLockBackend(client, key_prefix="acme:crons:")

        await backend.acquire_lock("job:report", 30)
        await backend.is_locked("job:report")

        assert client.keys == ["acme:crons:job:report"] * 2

    def test_config_exposes_the_prefix(self, monkeypatch):
        assert CronConfig().lock_key_prefix == DEFAULT_LOCK_KEY_PREFIX

        monkeypatch.setenv("CRON_LOCK_KEY_PREFIX", "team-a:")
        assert CronConfig().lock_key_prefix == "team-a:"


class TestBackendConstruction:
    """Backends accept a URL, not only a pre-built client."""

    def test_redis_lock_backend_accepts_a_url(self):
        backend = RedisLockBackend("redis://localhost:6379/0")

        assert backend.redis is not None
        assert hasattr(backend.redis, "set")

    def test_redis_lock_backend_still_accepts_a_client(self):
        client = RecordingRedis()

        assert RedisLockBackend(client).redis is client


class TestLocalLockBackendHousekeeping:
    """Expired entries are swept, since claim keys are never released."""

    async def test_expired_keys_do_not_accumulate(self):
        backend = LocalLockBackend()

        for i in range(50):
            await backend.acquire_lock(f"job:x:tick:{i}", ttl=0)

        await backend.acquire_lock("job:x:tick:final", ttl=60)

        assert len(backend.locks) == 1


class TestSQLAlchemyLockAtomicity:
    """Separate engines, as separate worker processes would have."""

    async def test_two_independent_backends_cannot_both_acquire(self, temp_db):
        sqlalchemy = pytest.importorskip("sqlalchemy.ext.asyncio")
        from fastapi_crons.locking.sqlalchemy import SQLAlchemyLockBackend

        url = f"sqlite+aiosqlite:///{temp_db}"
        a = SQLAlchemyLockBackend(sqlalchemy.create_async_engine(url))
        b = SQLAlchemyLockBackend(sqlalchemy.create_async_engine(url))

        # Serialised, then concurrent: neither may hand out the key twice.
        assert await a.acquire_lock("job:report", 60) is not None
        assert await b.acquire_lock("job:report", 60) is None

        both = await asyncio.gather(
            a.acquire_lock("job:other", 60), b.acquire_lock("job:other", 60)
        )
        assert sum(x is not None for x in both) == 1

        await a.dispose()
        await b.dispose()

    async def test_expired_lock_can_be_taken_over(self, temp_db):
        sqlalchemy = pytest.importorskip("sqlalchemy.ext.asyncio")
        from fastapi_crons.locking.sqlalchemy import SQLAlchemyLockBackend

        backend = SQLAlchemyLockBackend(
            sqlalchemy.create_async_engine(f"sqlite+aiosqlite:///{temp_db}")
        )

        assert await backend.acquire_lock("job:expiring", 0) is not None
        assert await backend.acquire_lock("job:expiring", 60) is not None

        await backend.dispose()


class TestJobStatusPersistence:
    """A terminal status must never be silently dropped."""

    async def test_terminal_status_without_prior_running_row(self, temp_db):
        state = SQLiteStateBackend(temp_db)

        await state.set_job_status("orphan", "completed", "inst-1")
        status = await state.get_job_status("orphan")
        await state.close()

        assert status is not None, "completed status was dropped"
        assert status["status"] == "completed"

    async def test_completion_from_a_different_instance_is_recorded(self, temp_db):
        state = SQLiteStateBackend(temp_db)

        await state.set_job_status("job", "running", "inst-1")
        # Another instance takes the row over, then the first one completes.
        await state.set_job_status("job", "running", "inst-2")
        await state.set_job_status("job", "completed", "inst-1")

        status = await state.get_job_status("job")
        await state.close()

        assert status["status"] == "completed", "job would be shown as running forever"

    async def test_sqlalchemy_state_backend_disposes_cleanly(self, temp_db):
        sqlalchemy = pytest.importorskip("sqlalchemy.ext.asyncio")
        from fastapi_crons.state.sqlalchemy import SQLAlchemyStateBackend

        backend = SQLAlchemyStateBackend(
            sqlalchemy.create_async_engine(f"sqlite+aiosqlite:///{temp_db}")
        )
        await backend.set_last_run("job", datetime.now(timezone.utc))

        await backend.dispose()  # used to raise NameError: AsyncEngine


class TestRouterPrefix:
    """The router can be mounted under a prefix without shadowing app routes."""

    def test_prefix_serves_endpoints_and_leaves_app_routes_alone(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from fastapi_crons import Crons, get_cron_router

        app = FastAPI()
        Crons()
        app.include_router(get_cron_router(), prefix="/crons")

        @app.get("/anything")
        def anything():
            return {"mine": True}

        client = TestClient(app)

        assert client.get("/crons").status_code == 200
        assert client.get("/crons/health").status_code == 200
        # Without a prefix the router's catch-all /{job_name} swallows this.
        assert client.get("/anything").json() == {"mine": True}

    def test_default_mount_is_unchanged(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from fastapi_crons import Crons, get_cron_router

        app = FastAPI()
        Crons()
        app.include_router(get_cron_router())

        assert TestClient(app).get("/health").status_code == 200
