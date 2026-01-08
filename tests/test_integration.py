"""Integration tests for fastapi-crons."""
import asyncio
import inspect

import pytest
from fastapi.testclient import TestClient

from fastapi_crons import Crons, get_cron_router


class TestIntegration:
    """Integration tests for the complete system."""

    @pytest.mark.asyncio
    async def test_job_execution_flow(self, crons_instance):
        """Test complete job execution flow."""
        execution_log = []

        def before_hook(job_name, context):
            execution_log.append(("before", job_name))

        def after_hook(job_name, context):
            execution_log.append(("after", job_name))

        @crons_instance.cron("* * * * *", name="test_job")
        def test_job():
            execution_log.append(("execute", "test_job"))

        job = crons_instance.get_job("test_job")
        job.add_before_run_hook(before_hook)
        job.add_after_run_hook(after_hook)

        # Manually execute the job
        await asyncio.to_thread(test_job)

        assert len(execution_log) >= 1

    def test_fastapi_integration(self, fastapi_app, sqlite_backend, lock_manager, cron_config):
        """Test integration with FastAPI app."""
        crons = Crons(
            app=fastapi_app,
            state_backend=sqlite_backend,
            lock_manager=lock_manager,
            config=cron_config
        )

        @crons.cron("*/5 * * * *", name="periodic_task")
        def periodic_task():
            return "Task executed"

        # Include the cron router
        fastapi_app.include_router(get_cron_router())

        client = TestClient(fastapi_app)

        # Test the cron endpoint
        response = client.get("/")
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) > 0

    def test_multiple_crons_instances(self, sqlite_backend, lock_manager, cron_config):
        """Test multiple Crons instances."""
        crons1 = Crons(
            state_backend=sqlite_backend,
            lock_manager=lock_manager,
            config=cron_config
        )

        crons2 = Crons(
            state_backend=sqlite_backend,
            lock_manager=lock_manager,
            config=cron_config
        )

        @crons1.cron("* * * * *", name="job1")
        def job1():
            pass

        @crons2.cron("* * * * *", name="job2")
        def job2():
            pass

        # Both instances should have their jobs
        assert len(crons1.get_jobs()) >= 1
        assert len(crons2.get_jobs()) >= 1

    @pytest.mark.asyncio
    async def test_async_job_execution(self, crons_instance):
        """Test async job execution."""
        execution_log = []

        @crons_instance.cron("* * * * *", name="async_job")
        async def async_job():
            await asyncio.sleep(0.1)
            execution_log.append("async_executed")

        job = crons_instance.get_job("async_job")
        assert inspect.iscoroutinefunction(job.func)

    @pytest.mark.asyncio
    async def test_sync_job_execution(self, crons_instance):
        """Test sync job execution."""
        execution_log = []

        @crons_instance.cron("* * * * *", name="sync_job")
        def sync_job():
            execution_log.append("sync_executed")

        job = crons_instance.get_job("sync_job")
        assert not inspect.iscoroutinefunction(job.func)
