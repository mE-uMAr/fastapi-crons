"""Tests for state backend implementations."""
import asyncio
from datetime import datetime, timedelta

import pytest


class TestSQLiteStateBackend:
    """Test suite for SQLite state backend."""

    @pytest.mark.asyncio
    async def test_set_and_get_last_run(self, sqlite_backend):
        """Test setting and retrieving last run timestamp."""
        job_name = "test_job"
        now = datetime.now()

        await sqlite_backend.set_last_run(job_name, now)
        last_run = await sqlite_backend.get_last_run(job_name)

        assert last_run is not None
        assert last_run == now.isoformat()

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_last_run(self, sqlite_backend):
        """Test getting last run for a job that doesn't exist."""
        last_run = await sqlite_backend.get_last_run("nonexistent_job")
        assert last_run is None

    @pytest.mark.asyncio
    async def test_update_last_run(self, sqlite_backend):
        """Test updating last run timestamp."""
        job_name = "test_job"
        first_time = datetime.now()
        second_time = datetime.now() + timedelta(minutes=5)

        await sqlite_backend.set_last_run(job_name, first_time)
        first_result = await sqlite_backend.get_last_run(job_name)

        await sqlite_backend.set_last_run(job_name, second_time)
        second_result = await sqlite_backend.get_last_run(job_name)

        assert first_result == first_time.isoformat()
        assert second_result == second_time.isoformat()

    @pytest.mark.asyncio
    async def test_get_all_jobs(self, sqlite_backend):
        """Test retrieving all jobs."""
        now = datetime.now()

        await sqlite_backend.set_last_run("job1", now)
        await sqlite_backend.set_last_run("job2", now + timedelta(minutes=1))

        all_jobs = await sqlite_backend.get_all_jobs()

        assert len(all_jobs) == 2
        assert all_jobs[0][0] == "job1"
        assert all_jobs[1][0] == "job2"

    @pytest.mark.asyncio
    async def test_set_job_status(self, sqlite_backend):
        """Test setting job status."""
        job_name = "test_job"
        instance_id = "instance_1"

        await sqlite_backend.set_job_status(job_name, "running", instance_id)
        status = await sqlite_backend.get_job_status(job_name)

        assert status is not None
        assert status["status"] == "running"
        assert status["instance_id"] == instance_id

    @pytest.mark.asyncio
    async def test_update_job_status(self, sqlite_backend):
        """Test updating job status."""
        job_name = "test_job"
        instance_id = "instance_1"

        await sqlite_backend.set_job_status(job_name, "running", instance_id)
        await sqlite_backend.set_job_status(job_name, "completed", instance_id)

        status = await sqlite_backend.get_job_status(job_name)
        assert status["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_status(self, sqlite_backend):
        """Test getting status for a job that doesn't exist."""
        status = await sqlite_backend.get_job_status("nonexistent_job")
        assert status is None

    @pytest.mark.asyncio
    async def test_log_job_execution(self, sqlite_backend):
        """Test logging job execution."""
        job_name = "test_job"
        instance_id = "instance_1"
        start_time = datetime.now()
        end_time = datetime.now() + timedelta(seconds=5)
        duration = 5.0

        await sqlite_backend.log_job_execution(
            job_name, instance_id, "completed",
            start_time, end_time, duration
        )

        # Verify the log was created (by checking no exception was raised)
        # In a real scenario, you'd query the execution log table

    @pytest.mark.asyncio
    async def test_log_job_execution_with_error(self, sqlite_backend):
        """Test logging job execution with error."""
        job_name = "test_job"
        instance_id = "instance_1"
        start_time = datetime.now()
        end_time = datetime.now() + timedelta(seconds=2)
        duration = 2.0
        error_msg = "Job failed with error"

        await sqlite_backend.log_job_execution(
            job_name, instance_id, "failed",
            start_time, end_time, duration, error_msg
        )

        # Verify the log was created

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, sqlite_backend):
        """Test concurrent writes to the database."""
        async def write_job(job_num):
            await sqlite_backend.set_last_run(f"job_{job_num}", datetime.now())

        # Run 10 concurrent writes
        await asyncio.gather(*[write_job(i) for i in range(10)])

        all_jobs = await sqlite_backend.get_all_jobs()
        assert len(all_jobs) == 10
