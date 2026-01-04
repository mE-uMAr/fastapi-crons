"""Tests for CronJob class and job creation."""
from datetime import datetime, timezone

import pytest
from croniter import CroniterBadCronError

from fastapi_crons import CronJob


class TestCronJob:
    """Test suite for CronJob class."""

    def test_job_creation(self):
        """Test basic job creation."""
        def sample_job():
            pass

        job = CronJob(sample_job, "*/5 * * * *", name="test_job")

        assert job.name == "test_job"
        assert job.expr == "*/5 * * * *"
        assert job.func == sample_job
        assert job.tags == []
        assert job.last_run is None

    def test_job_with_tags(self):
        """Test job creation with tags."""
        def sample_job():
            pass

        job = CronJob(sample_job, "0 0 * * *", name="daily_job", tags=["daily", "maintenance"])

        assert job.tags == ["daily", "maintenance"]

    def test_job_name_defaults_to_function_name(self):
        """Test that job name defaults to function name."""
        def my_function():
            pass

        job = CronJob(my_function, "* * * * *")
        assert job.name == "my_function"

    def test_job_next_run_calculation(self):
        """Test that next_run is calculated correctly."""
        def sample_job():
            pass

        job = CronJob(sample_job, "*/5 * * * *")

        assert job.next_run is not None
        assert isinstance(job.next_run, datetime)
        # Next run should be in the future
        assert job.next_run > datetime.now(timezone.utc)

    def test_job_update_next_run(self):
        """Test updating next_run timestamp."""
        def sample_job():
            pass

        job = CronJob(sample_job, "*/5 * * * *")
        first_next_run = job.next_run

        job.update_next_run()
        second_next_run = job.next_run

        # Both should be in the future
        assert first_next_run > datetime.now(timezone.utc)
        assert second_next_run > datetime.now(timezone.utc)

    def test_job_hooks_initialization(self):
        """Test that job hooks are initialized as empty lists."""
        def sample_job():
            pass

        job = CronJob(sample_job, "* * * * *")

        assert job.before_run_hooks == []
        assert job.after_run_hooks == []
        assert job.on_error_hooks == []

    def test_add_before_run_hook(self):
        """Test adding a before_run hook."""
        def sample_job():
            pass

        def hook(job_name, context):
            pass

        job = CronJob(sample_job, "* * * * *")
        result = job.add_before_run_hook(hook)

        assert hook in job.before_run_hooks
        assert result == job  # Test method chaining

    def test_add_after_run_hook(self):
        """Test adding an after_run hook."""
        def sample_job():
            pass

        def hook(job_name, context):
            pass

        job = CronJob(sample_job, "* * * * *")
        result = job.add_after_run_hook(hook)

        assert hook in job.after_run_hooks
        assert result == job  # Test method chaining

    def test_add_on_error_hook(self):
        """Test adding an on_error hook."""
        def sample_job():
            pass

        def hook(job_name, context):
            pass

        job = CronJob(sample_job, "* * * * *")
        result = job.add_on_error_hook(hook)

        assert hook in job.on_error_hooks
        assert result == job  # Test method chaining

    def test_multiple_hooks(self):
        """Test adding multiple hooks of the same type."""
        def sample_job():
            pass

        def hook1(job_name, context):
            pass

        def hook2(job_name, context):
            pass

        job = CronJob(sample_job, "* * * * *")
        job.add_before_run_hook(hook1)
        job.add_before_run_hook(hook2)

        assert len(job.before_run_hooks) == 2
        assert hook1 in job.before_run_hooks
        assert hook2 in job.before_run_hooks

    def test_cron_expression_validation(self):
        """Test that invalid cron expressions raise errors."""
        def sample_job():
            pass

        with pytest.raises(CroniterBadCronError):
            CronJob(sample_job, "invalid cron expression")

    def test_valid_cron_expressions(self):
        """Test various valid cron expressions."""
        def sample_job():
            pass

        valid_expressions = [
            "* * * * *",           # Every minute
            "*/5 * * * *",         # Every 5 minutes
            "0 * * * *",           # Every hour
            "0 0 * * *",           # Daily at midnight
            "0 0 * * 0",           # Weekly on Sunday
            "0 0 1 * *",           # Monthly on 1st
            "0 0 1 1 *",           # Yearly on Jan 1st
        ]

        for expr in valid_expressions:
            job = CronJob(sample_job, expr)
            assert job.expr == expr
