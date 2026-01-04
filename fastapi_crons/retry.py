"""
Retry decorator and utilities for job failures.

This module provides a configurable retry mechanism for cron jobs
with exponential backoff, jitter, and exception filtering.
"""
import asyncio
import functools
import inspect
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import ParamSpec, TypeVar

logger = logging.getLogger("fastapi_cron.retry")

P = ParamSpec("P")
T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries)
        retry_delay: Initial delay between retries in seconds
        backoff_multiplier: Multiplier for exponential backoff (e.g., 2.0 doubles delay each retry)
        max_delay: Maximum delay between retries in seconds
        jitter: Whether to add random jitter to delay (helps prevent thundering herd)
        retry_on: Tuple of exception types to retry on (None = retry on all exceptions)
    """
    max_retries: int = 3
    retry_delay: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay: float = 300.0
    jitter: bool = True
    retry_on: tuple[type[Exception], ...] | None = None
    on_retry: Callable[[int, Exception, float], None] | None = None


def _calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for the next retry attempt with exponential backoff."""
    delay = config.retry_delay * (config.backoff_multiplier ** attempt)
    delay = min(delay, config.max_delay)

    if config.jitter:
        # Add up to 25% jitter
        jitter_amount = delay * 0.25 * random.random()
        delay = delay + jitter_amount

    return delay


def _should_retry(exception: Exception, config: RetryConfig) -> bool:
    """Determine if the exception should trigger a retry."""
    if config.retry_on is None:
        return True
    return isinstance(exception, config.retry_on)


def retry_on_failure(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    max_delay: float = 300.0,
    jitter: bool = True,
    retry_on: tuple[type[Exception], ...] | None = None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to retry a function on failure with exponential backoff.

    This decorator can be applied to both sync and async functions.
    It will retry the function up to max_retries times with exponential
    backoff between attempts.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Initial delay between retries in seconds (default: 1.0)
        backoff_multiplier: Multiplier for exponential backoff (default: 2.0)
        max_delay: Maximum delay between retries in seconds (default: 300.0)
        jitter: Whether to add random jitter to delay (default: True)
        retry_on: Tuple of exception types to retry on (default: None = all exceptions)
        on_retry: Callback function called on each retry with (attempt, exception, delay)

    Returns:
        Decorated function with retry behavior

    Example:
        >>> @retry_on_failure(max_retries=3, retry_delay=1.0)
        ... async def fetch_data():
        ...     # This will be retried up to 3 times on failure
        ...     response = await http_client.get(url)
        ...     return response.json()

        >>> @retry_on_failure(retry_on=(ConnectionError, TimeoutError))
        ... def connect_to_database():
        ...     # Only retry on specific exceptions
        ...     return database.connect()
    """
    config = RetryConfig(
        max_retries=max_retries,
        retry_delay=retry_delay,
        backoff_multiplier=backoff_multiplier,
        max_delay=max_delay,
        jitter=jitter,
        retry_on=retry_on,
        on_retry=on_retry,
    )

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                last_exception: Exception | None = None

                for attempt in range(config.max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e

                        if not _should_retry(e, config):
                            logger.debug(f"Exception {type(e).__name__} not in retry list, raising")
                            raise

                        if attempt < config.max_retries:
                            delay = _calculate_delay(attempt, config)
                            logger.warning(
                                f"Attempt {attempt + 1}/{config.max_retries + 1} failed: {e}. "
                                f"Retrying in {delay:.2f}s..."
                            )

                            if config.on_retry:
                                try:
                                    config.on_retry(attempt + 1, e, delay)
                                except Exception as hook_error:
                                    logger.error(f"on_retry callback failed: {hook_error}")

                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                f"All {config.max_retries + 1} attempts failed. "
                                f"Last error: {e}"
                            )

                # This should never be reached, but just in case
                if last_exception:
                    raise last_exception
                raise RuntimeError("Unexpected state in retry decorator")

            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                import time
                last_exception: Exception | None = None

                for attempt in range(config.max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e

                        if not _should_retry(e, config):
                            logger.debug(f"Exception {type(e).__name__} not in retry list, raising")
                            raise

                        if attempt < config.max_retries:
                            delay = _calculate_delay(attempt, config)
                            logger.warning(
                                f"Attempt {attempt + 1}/{config.max_retries + 1} failed: {e}. "
                                f"Retrying in {delay:.2f}s..."
                            )

                            if config.on_retry:
                                try:
                                    config.on_retry(attempt + 1, e, delay)
                                except Exception as hook_error:
                                    logger.error(f"on_retry callback failed: {hook_error}")

                            time.sleep(delay)
                        else:
                            logger.error(
                                f"All {config.max_retries + 1} attempts failed. "
                                f"Last error: {e}"
                            )

                # This should never be reached, but just in case
                if last_exception:
                    raise last_exception
                raise RuntimeError("Unexpected state in retry decorator")

            return sync_wrapper  # type: ignore

    return decorator


async def execute_with_retry(
    func: Callable[[], T] | Callable[[], Awaitable[T]],
    config: RetryConfig,
    job_name: str = "unnamed",
) -> T:
    """
    Execute a function with retry logic.

    This is an alternative to the decorator for cases where you need
    to apply retry logic dynamically.

    Args:
        func: The function to execute (sync or async)
        config: Retry configuration
        job_name: Name of the job for logging purposes

    Returns:
        The result of the function

    Raises:
        The last exception if all retries are exhausted
    """
    last_exception: Exception | None = None
    is_async = inspect.iscoroutinefunction(func)

    for attempt in range(config.max_retries + 1):
        try:
            if is_async:
                return await func()  # type: ignore
            else:
                return await asyncio.to_thread(func)  # type: ignore
        except Exception as e:
            last_exception = e

            if not _should_retry(e, config):
                logger.debug(f"[{job_name}] Exception {type(e).__name__} not in retry list, raising")
                raise

            if attempt < config.max_retries:
                delay = _calculate_delay(attempt, config)
                logger.warning(
                    f"[{job_name}] Attempt {attempt + 1}/{config.max_retries + 1} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )

                if config.on_retry:
                    try:
                        config.on_retry(attempt + 1, e, delay)
                    except Exception as hook_error:
                        logger.error(f"[{job_name}] on_retry callback failed: {hook_error}")

                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"[{job_name}] All {config.max_retries + 1} attempts failed. "
                    f"Last error: {e}"
                )

    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected state in execute_with_retry")
