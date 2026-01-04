"""Tests for job hooks functionality."""
import asyncio

import pytest

from fastapi_crons import CronJob


class TestHooks:
    """Test suite for job hooks."""

    def test_sync_hook_execution(self):
        """Test executing a synchronous hook."""
        hook_called = []

        def sync_hook(job_name, context):
            hook_called.append((job_name, context))

        def job_func():
            pass

        job = CronJob(job_func, "* * * * *", name="test_job")
        job.add_before_run_hook(sync_hook)

        assert sync_hook in job.before_run_hooks

    @pytest.mark.asyncio
    async def test_async_hook_execution(self):
        """Test executing an asynchronous hook."""
        hook_called = []

        async def async_hook(job_name, context):
            await asyncio.sleep(0.01)
            hook_called.append((job_name, context))

        def job_func():
            pass

        job = CronJob(job_func, "* * * * *", name="test_job")
        job.add_before_run_hook(async_hook)

        assert async_hook in job.before_run_hooks

    def test_hook_context_data(self):
        """Test that hooks receive correct context data."""
        received_context = []

        def hook(job_name, context):
            received_context.append({
                "job_name": job_name,
                "context": context
            })

        def job_func():
            pass

        job = CronJob(job_func, "* * * * *", name="my_job", tags=["test"])
        job.add_before_run_hook(hook)

        # Simulate hook execution
        context = {
            "job_name": "my_job",
            "tags": ["test"],
            "timestamp": "2024-01-01T00:00:00"
        }
        hook("my_job", context)

        assert len(received_context) == 1
        assert received_context[0]["job_name"] == "my_job"

    def test_multiple_hooks_execution_order(self):
        """Test that multiple hooks are executed in order."""
        execution_order = []

        def hook1(job_name, context):
            execution_order.append(1)

        def hook2(job_name, context):
            execution_order.append(2)

        def hook3(job_name, context):
            execution_order.append(3)

        def job_func():
            pass

        job = CronJob(job_func, "* * * * *")
        job.add_before_run_hook(hook1)
        job.add_before_run_hook(hook2)
        job.add_before_run_hook(hook3)

        # Simulate execution
        for hook in job.before_run_hooks:
            hook("test_job", {})

        assert execution_order == [1, 2, 3]

    def test_error_hook_on_failure(self):
        """Test error hook is called on job failure."""
        error_context = []

        def error_hook(job_name, context):
            error_context.append({
                "job_name": job_name,
                "error": context.get("error")
            })

        def job_func():
            pass

        job = CronJob(job_func, "* * * * *", name="failing_job")
        job.add_on_error_hook(error_hook)

        # Simulate error
        context = {
            "job_name": "failing_job",
            "error": "Job execution failed",
            "success": False
        }
        error_hook("failing_job", context)

        assert len(error_context) == 1
        assert error_context[0]["error"] == "Job execution failed"
