"""Tests for Crons scheduler class."""

import pytest

from fastapi_crons import CronConfig, Crons


class TestCronsScheduler:
    """Test suite for Crons scheduler."""

    def test_crons_initialization(self, crons_instance):
        """Test basic Crons initialization."""
        assert crons_instance.jobs == []
        assert crons_instance._running is False
        assert crons_instance.config is not None

    def test_crons_with_custom_config(self, sqlite_backend, lock_manager):
        """Test Crons initialization with custom config."""
        config = CronConfig()
        config.enable_distributed_locking = True

        crons = Crons(
            state_backend=sqlite_backend,
            lock_manager=lock_manager,
            config=config
        )

        assert crons.config.enable_distributed_locking is True

    def test_register_job_with_decorator(self, crons_instance):
        """Test registering a job with decorator."""
        @crons_instance.cron("*/5 * * * *", name="test_job")
        def my_job():
            pass

        assert len(crons_instance.jobs) == 1
        assert crons_instance.jobs[0].name == "test_job"

    def test_register_multiple_jobs(self, crons_instance):
        """Test registering multiple jobs."""
        @crons_instance.cron("*/5 * * * *", name="job1")
        def job1():
            pass

        @crons_instance.cron("0 * * * *", name="job2")
        def job2():
            pass

        assert len(crons_instance.jobs) == 2

    def test_get_jobs(self, crons_instance):
        """Test retrieving all jobs."""
        @crons_instance.cron("* * * * *", name="job1")
        def job1():
            pass

        jobs = crons_instance.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].name == "job1"

    def test_get_job_by_name(self, crons_instance):
        """Test retrieving a specific job by name."""
        @crons_instance.cron("* * * * *", name="specific_job")
        def specific_job_func():
            pass

        job = crons_instance.get_job("specific_job")
        assert job is not None
        assert job.name == "specific_job"

    def test_get_nonexistent_job(self, crons_instance):
        """Test retrieving a job that doesn't exist."""
        job = crons_instance.get_job("nonexistent")
        assert job is None

    def test_add_before_run_hook_to_specific_job(self, crons_instance):
        """Test adding a hook to a specific job."""
        @crons_instance.cron("* * * * *", name="job1")
        def job1():
            pass

        def hook(job_name, context):
            pass

        crons_instance.add_before_run_hook(hook, job_name="job1")

        job = crons_instance.get_job("job1")
        assert hook in job.before_run_hooks

    def test_add_hook_to_all_jobs(self, crons_instance):
        """Test adding a hook to all jobs."""
        @crons_instance.cron("* * * * *", name="job1")
        def job1():
            pass

        @crons_instance.cron("* * * * *", name="job2")
        def job2():
            pass

        def hook(job_name, context):
            pass

        crons_instance.add_before_run_hook(hook)

        assert hook in crons_instance.get_job("job1").before_run_hooks
        assert hook in crons_instance.get_job("job2").before_run_hooks

    def test_hook_chaining(self, crons_instance):
        """Test method chaining for hook addition."""
        @crons_instance.cron("* * * * *", name="job1")
        def job1():
            pass

        def hook1(job_name, context):
            pass

        def hook2(job_name, context):
            pass

        result = (crons_instance
                  .add_before_run_hook(hook1)
                  .add_after_run_hook(hook2))

        assert result == crons_instance

    @pytest.mark.asyncio
    async def test_start_scheduler(self, crons_instance):
        """Test starting the scheduler."""
        @crons_instance.cron("* * * * *", name="job1")
        def job1():
            pass

        await crons_instance.start()
        assert crons_instance._running is True

        await crons_instance.stop()

    @pytest.mark.asyncio
    async def test_stop_scheduler(self, crons_instance):
        """Test stopping the scheduler."""
        @crons_instance.cron("* * * * *", name="job1")
        def job1():
            pass

        await crons_instance.start()
        await crons_instance.stop()

        assert crons_instance._running is False

    @pytest.mark.asyncio
    async def test_start_already_running(self, crons_instance):
        """Test starting scheduler when already running."""
        @crons_instance.cron("* * * * *", name="job1")
        def job1():
            pass

        await crons_instance.start()
        initial_tasks = len(crons_instance._tasks)

        # Try to start again
        await crons_instance.start()

        # Should not create duplicate tasks
        assert len(crons_instance._tasks) == initial_tasks

        await crons_instance.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, crons_instance):
        """Test stopping scheduler when not running."""
        # Should not raise an error
        await crons_instance.stop()
        assert crons_instance._running is False
