import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any

from .config import CronConfig
from .job import CronJob, HookFunc
from .locking import DistributedLockManager
from .state import StateBackend

logger = logging.getLogger("fastapi_cron.runner")


class JobTimeoutError(Exception):
    """Raised when a job execution exceeds its timeout."""

    def __init__(self, job_name: str, timeout: float):
        self.job_name = job_name
        self.timeout = timeout
        super().__init__(f"Job '{job_name}' timed out after {timeout:.2f} seconds")


async def execute_hook(hook: HookFunc, job_name: str, context: dict) -> None:
    """Execute a hook function, handling both sync and async hooks."""
    try:
        if inspect.iscoroutinefunction(hook):
            await hook(job_name, context)
        else:
            await asyncio.to_thread(hook, job_name, context)
    except Exception as e:
        logger.error(f"[Hook Error][{job_name}] {e}")


async def execute_job_with_timeout(
    job: CronJob,
    timeout: float | None,
) -> Any:
    """Execute a job with optional timeout."""
    if asyncio.iscoroutinefunction(job.func):
        coro = job.func()
    else:
        coro = asyncio.to_thread(job.func)

    if timeout is not None and timeout > 0:
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise JobTimeoutError(job.name, timeout) from None
    else:
        return await coro


def calculate_retry_delay(
    attempt: int,
    base_delay: float,
    backoff_multiplier: float,
    max_delay: float,
) -> float:
    """Calculate delay for the next retry attempt with exponential backoff and jitter."""
    import random

    delay = base_delay * (backoff_multiplier ** attempt)
    delay = min(delay, max_delay)
    # Add up to 25% jitter to prevent thundering herd
    jitter_amount = delay * 0.25 * random.random()
    return delay + jitter_amount


async def run_job_loop(job: CronJob, state: StateBackend, lock_manager: DistributedLockManager, config: CronConfig) -> None:
    """Main job execution loop with distributed locking, retry, and timeout support."""
    logger.info(f"Starting job loop for '{job.name}' - next run at {job.next_run}")

    # Resolve retry configuration (job-level overrides config-level)
    max_retries = job.max_retries if job.max_retries is not None else config.default_max_retries
    retry_delay = job.retry_delay if job.retry_delay is not None else config.default_retry_delay
    timeout = job.timeout if job.timeout is not None else config.default_job_timeout

    while True:
        try:
            now = datetime.now(timezone.utc)
            seconds = (job.next_run - now).total_seconds()

            if seconds > 0:
                logger.debug(f"Job '{job.name}' waiting {seconds:.1f} seconds until next run")
                await asyncio.sleep(seconds)

            # Try to acquire distributed lock
            lock_key = f"job:{job.name}"
            lock_id = await lock_manager.acquire_lock(lock_key)

            if not lock_id:
                logger.info(f"Job '{job.name}' is locked by another instance, skipping")
                job.update_next_run()
                continue

            try:
                # Set job status to running
                await state.set_job_status(job.name, "running", config.instance_id)

                # Create context for hooks
                context: dict[str, Any] = {
                    "job_name": job.name,
                    "scheduled_time": job.next_run.isoformat(),
                    "actual_time": datetime.now(timezone.utc).isoformat(),
                    "tags": job.tags,
                    "expr": job.expr,
                    "instance_id": config.instance_id,
                    "max_retries": max_retries,
                    "timeout": timeout,
                }

                # Execute before_run hooks
                for hook in job.before_run_hooks:
                    await execute_hook(hook, job.name, context)

                start_time = datetime.now(timezone.utc)
                last_error: Exception | None = None
                attempt = 0

                # Retry loop
                while attempt <= max_retries:
                    try:
                        logger.info(
                            f"Executing job '{job.name}' on instance {config.instance_id}"
                            f"{f' (attempt {attempt + 1}/{max_retries + 1})' if max_retries > 0 else ''}"
                        )

                        result = await execute_job_with_timeout(job, timeout)

                        end_time = datetime.now(timezone.utc)
                        duration = (end_time - start_time).total_seconds()

                        job.last_run = end_time
                        await state.set_last_run(job.name, end_time)
                        await state.set_job_status(job.name, "completed", config.instance_id)

                        # Update context with execution details
                        context.update({
                            "success": True,
                            "start_time": start_time.isoformat(),
                            "end_time": end_time.isoformat(),
                            "duration": duration,
                            "result": result,
                            "attempts": attempt + 1,
                        })

                        # Execute after_run hooks
                        for hook in job.after_run_hooks:
                            await execute_hook(hook, job.name, context)

                        # Log execution
                        await state.log_job_execution(
                            job.name, config.instance_id, "completed",
                            start_time, end_time, duration
                        )

                        logger.info(f"Job '{job.name}' completed successfully in {duration:.2f}s")
                        break  # Success, exit retry loop

                    except Exception as e:
                        last_error = e
                        is_timeout = isinstance(e, JobTimeoutError)

                        # Check if we should retry this exception
                        should_retry = True
                        if job.retry_on is not None:
                            should_retry = isinstance(e, job.retry_on)

                        if attempt < max_retries and should_retry and not is_timeout:
                            # Calculate delay for next retry
                            delay = calculate_retry_delay(
                                attempt,
                                retry_delay,
                                config.retry_backoff_multiplier,
                                config.max_retry_delay,
                            )
                            logger.warning(
                                f"Job '{job.name}' attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                                f"Retrying in {delay:.2f}s..."
                            )
                            await asyncio.sleep(delay)
                            attempt += 1
                        else:
                            # All retries exhausted or non-retryable error
                            break

                # Handle final failure (after all retries)
                if last_error is not None and (attempt >= max_retries or isinstance(last_error, JobTimeoutError)):
                    end_time = datetime.now(timezone.utc)
                    duration = (end_time - start_time).total_seconds()
                    error = str(last_error)

                    logger.error(f"Job '{job.name}' failed after {attempt + 1} attempt(s): {error}")

                    await state.set_job_status(job.name, "failed", config.instance_id)

                    # Update context with error details
                    context.update({
                        "success": False,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "duration": duration,
                        "error": error,
                        "attempts": attempt + 1,
                        "is_timeout": isinstance(last_error, JobTimeoutError),
                    })

                    # Execute on_error hooks
                    for hook in job.on_error_hooks:
                        await execute_hook(hook, job.name, context)

                    # Log execution
                    await state.log_job_execution(
                        job.name, config.instance_id, "failed",
                        start_time, end_time, duration, error
                    )

            finally:
                # Always release the lock
                await lock_manager.release_lock(lock_key)

            job.update_next_run()
            logger.debug(f"Job '{job.name}' next run scheduled for {job.next_run}")

        except asyncio.CancelledError:
            logger.info(f"Job loop for '{job.name}' was cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in job loop for '{job.name}': {e}")
            # Wait a bit before retrying to avoid tight error loops
            await asyncio.sleep(60)
