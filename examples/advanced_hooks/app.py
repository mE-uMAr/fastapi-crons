"""
Advanced Hooks Example for FastAPI-Crons

This example demonstrates the powerful hooks system:
- Before-run hooks for job preparation
- After-run hooks for success handling
- On-error hooks for failure handling
- Built-in hooks for logging, alerts, and metrics
- Custom hooks for specific use cases

Run with:
    uvicorn app:app --reload

Then visit:
    - http://localhost:8000/crons  - View jobs with hook counts
    - http://localhost:8000/metrics - View collected metrics
"""

import logging
from typing import Any

from fastapi import FastAPI

from fastapi_crons import (
    Crons,
    alert_on_failure,
    alert_on_long_duration,
    get_cron_router,
    log_job_error,
    # Built-in hooks
    log_job_start,
    log_job_success,
    metrics_collector,
)

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    title="FastAPI-Crons Advanced Hooks Example",
    description="Demonstrates the hooks system for job lifecycle management",
)

crons = Crons(app)
app.include_router(get_cron_router(), prefix="/crons", tags=["Cron Jobs"])


# =============================================================================
# CUSTOM HOOKS
# =============================================================================

def custom_before_hook(job_name: str, context: dict[str, Any]):
    """
    Custom before-run hook.

    This hook is called BEFORE the job function executes.
    Use it for:
    - Logging job start
    - Acquiring resources
    - Setting up database connections
    - Sending notifications that a job is starting
    """
    logger.info(f"🚀 [BEFORE] Job '{job_name}' is about to start")
    logger.info(f"   Scheduled time: {context.get('scheduled_time')}")
    logger.info(f"   Tags: {context.get('tags')}")


def custom_after_hook(job_name: str, context: dict[str, Any]):
    """
    Custom after-run hook.

    This hook is called AFTER the job completes SUCCESSFULLY.
    Use it for:
    - Logging success
    - Releasing resources
    - Sending success notifications
    - Recording metrics
    """
    duration = context.get("duration", 0)
    result = context.get("result")

    logger.info(f"✅ [AFTER] Job '{job_name}' completed successfully")
    logger.info(f"   Duration: {duration:.2f}s")
    logger.info(f"   Result: {result}")


def custom_error_hook(job_name: str, context: dict[str, Any]):
    """
    Custom on-error hook.

    This hook is called when the job FAILS.
    Use it for:
    - Logging errors
    - Sending alerts
    - Recording failure metrics
    - Triggering recovery procedures
    """
    error = context.get("error", "Unknown error")
    duration = context.get("duration", 0)

    logger.error(f"❌ [ERROR] Job '{job_name}' failed!")
    logger.error(f"   Duration: {duration:.2f}s")
    logger.error(f"   Error: {error}")


async def async_notification_hook(job_name: str, context: dict[str, Any]):
    """
    Async hook for sending notifications.

    Hooks can be async! Use async hooks for:
    - Making HTTP requests
    - Sending emails
    - Writing to databases
    - Calling external APIs
    """
    import asyncio

    # Simulate sending a notification
    logger.info(f"📧 Sending notification for job '{job_name}'...")
    await asyncio.sleep(0.1)  # Simulate network call
    logger.info("📧 Notification sent!")


def performance_tracking_hook(job_name: str, context: dict[str, Any]):
    """
    Hook for tracking job performance.

    Records execution time and sends alerts for slow jobs.
    """
    duration = context.get("duration", 0)
    threshold = 5.0  # 5 seconds

    if duration > threshold:
        logger.warning(
            f"⚠️ SLOW JOB: '{job_name}' took {duration:.2f}s "
            f"(threshold: {threshold}s)"
        )


# =============================================================================
# CRON JOBS WITH HOOKS
# =============================================================================

# Job with individual hooks attached via method chaining
@crons.cron("*/2 * * * *", name="job_with_hooks")
def job_with_individual_hooks():
    """
    Job with hooks attached individually.

    Hooks are attached using the .add_*_hook() methods.
    """
    logger.info("Executing job with individual hooks...")
    return {"status": "success"}


# Get the job and add hooks (method chaining)
job = crons.get_job("job_with_hooks")
if job:
    job.add_before_run_hook(custom_before_hook)
    job.add_after_run_hook(custom_after_hook)
    job.add_after_run_hook(performance_tracking_hook)
    job.add_on_error_hook(custom_error_hook)


# Job that uses built-in logging hooks
@crons.cron("*/3 * * * *", name="logged_job", tags=["logged"])
def job_with_builtin_logging():
    """
    Job using built-in logging hooks.
    """
    logger.info("Executing logged job...")
    return "Logged job completed"


# Attach built-in hooks
logged_job = crons.get_job("logged_job")
if logged_job:
    logged_job.add_before_run_hook(log_job_start)
    logged_job.add_after_run_hook(log_job_success)
    logged_job.add_on_error_hook(log_job_error)


# Job that uses the metrics collector
@crons.cron("*/2 * * * *", name="metrified_job", tags=["metrics"])
async def job_with_metrics():
    """
    Job with metrics collection.

    Uses the built-in metrics_collector to track:
    - Job run count
    - Success/failure counts
    - Execution duration
    """
    import asyncio
    import random

    # Simulate variable execution time
    await asyncio.sleep(random.uniform(0.1, 1.0))

    # Occasionally fail to demonstrate failure metrics
    if random.random() < 0.1:  # 10% failure rate
        raise ValueError("Random failure for testing")

    return "Metrics job completed"


# Attach metrics hooks
metrics_job = crons.get_job("metrified_job")
if metrics_job:
    metrics_job.add_before_run_hook(metrics_collector.record_job_start)
    metrics_job.add_after_run_hook(metrics_collector.record_job_success)
    metrics_job.add_on_error_hook(metrics_collector.record_job_failure)


# Job with alert on long duration
@crons.cron("*/5 * * * *", name="slow_job", tags=["alerts"])
async def potentially_slow_job():
    """
    Job that might take a long time.

    Uses alert_on_long_duration hook to send alerts
    when the job exceeds a time threshold.
    """
    import asyncio
    import random

    # Simulate variable execution time (sometimes slow)
    delay = random.uniform(0.5, 3.0)
    await asyncio.sleep(delay)

    return f"Completed in {delay:.2f}s"


# Attach long duration alert (triggers if job takes > 2 seconds)
slow_job = crons.get_job("slow_job")
if slow_job:
    slow_job.add_before_run_hook(log_job_start)
    slow_job.add_after_run_hook(alert_on_long_duration(threshold_seconds=2.0))
    slow_job.add_on_error_hook(alert_on_failure)


# =============================================================================
# GLOBAL HOOKS (Applied to all jobs)
# =============================================================================

# You can add hooks to ALL jobs at once using the Crons instance
# (Uncomment to enable global hooks)

# crons.add_before_run_hook(log_job_start)
# crons.add_after_run_hook(log_job_success)
# crons.add_on_error_hook(log_job_error)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
def root():
    """Root endpoint with usage information."""
    return {
        "message": "FastAPI-Crons Advanced Hooks Example",
        "endpoints": {
            "/crons": "View all jobs with hook counts",
            "/crons/health": "Health check",
            "/metrics": "View collected metrics",
            "/metrics/{job_name}": "View metrics for specific job",
        },
    }


@app.get("/metrics")
def get_all_metrics():
    """Get all collected metrics from the metrics collector."""
    return {
        "metrics": metrics_collector.get_metrics(),
        "description": {
            "job_runs": "Total number of times each job has started",
            "job_durations": "List of execution times for each job",
            "job_successes": "Number of successful completions",
            "job_failures": "Number of failures",
        },
    }


@app.get("/metrics/{job_name}")
def get_job_metrics(job_name: str):
    """Get metrics for a specific job."""
    job_metrics = metrics_collector.get_job_metrics(job_name)
    return {
        "job_name": job_name,
        "metrics": job_metrics,
    }


# =============================================================================
# HOOK TYPES SUMMARY
# =============================================================================
"""
HOOK TYPES:

1. BEFORE-RUN HOOKS
   - Called before job execution starts
   - Use for: preparation, logging, resource acquisition
   - Signature: (job_name: str, context: dict) -> None

2. AFTER-RUN HOOKS
   - Called after successful job completion
   - Use for: logging, metrics, notifications, cleanup
   - Signature: (job_name: str, context: dict) -> None
   - Context includes: success, duration, result, start_time, end_time

3. ON-ERROR HOOKS
   - Called when job fails with an exception
   - Use for: error logging, alerts, recovery
   - Signature: (job_name: str, context: dict) -> None
   - Context includes: error, duration, start_time, end_time

HOOK CONTEXT:
The context dict contains:
- job_name: Name of the job
- scheduled_time: When the job was scheduled to run
- actual_time: When it actually started
- tags: List of job tags
- expr: Cron expression
- instance_id: ID of the running instance

After completion, context also includes:
- success: True/False
- start_time: ISO timestamp
- end_time: ISO timestamp
- duration: Execution time in seconds
- result: Return value (if successful)
- error: Error message (if failed)
"""
