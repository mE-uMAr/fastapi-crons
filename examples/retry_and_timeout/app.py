"""
Retry and Timeout Example for FastAPI-Crons

This example demonstrates:
- Retry decorator for failed jobs with exponential backoff
- Job timeout configuration to prevent hung jobs
- Exception filtering (retry only on specific exceptions)
- Retry callbacks for monitoring retry attempts

Run with:
    uvicorn app:app --reload

Then visit:
    - http://localhost:8000/crons  - View jobs with retry/timeout config
    - http://localhost:8000/crons/health - Health check
"""

import asyncio
import logging
import random
from datetime import datetime

from fastapi import FastAPI

from fastapi_crons import (
    Crons,
    # Timeout error
    RetryConfig,
    execute_with_retry,
    get_cron_router,
    retry_on_failure,
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
    title="FastAPI-Crons Retry and Timeout Example",
    description="Demonstrates retry decorator and timeout configuration",
)

crons = Crons(app)
app.include_router(get_cron_router(), prefix="/crons", tags=["Cron Jobs"])


# =============================================================================
# CUSTOM EXCEPTIONS for retry filtering
# =============================================================================

class TransientError(Exception):
    """A transient error that can be retried."""


class PermanentError(Exception):
    """A permanent error that should not be retried."""


class NetworkError(Exception):
    """Simulated network error."""


class DatabaseError(Exception):
    """Simulated database error."""


# =============================================================================
# RETRY CALLBACK for monitoring
# =============================================================================

def on_retry_callback(attempt: int, exception: Exception, delay: float):
    """
    Callback function called on each retry attempt.

    Use this for:
    - Logging retry attempts
    - Sending alerts
    - Recording retry metrics
    """
    logger.warning(
        f"🔄 Retry attempt {attempt}: {type(exception).__name__}: {exception}. "
        f"Next retry in {delay:.2f}s"
    )


# =============================================================================
# CRON JOBS WITH RETRY
# =============================================================================

# Job with retry using cron decorator parameters
@crons.cron(
    "*/2 * * * *",
    name="job_with_retry",
    max_retries=3,           # Retry up to 3 times
    retry_delay=2.0,         # Initial delay of 2 seconds
    tags=["retry"]
)
async def job_with_retry():
    """
    Job configured with retry at the decorator level.

    Using decorator parameters is the simplest way to add retry.
    The job will retry up to 3 times with exponential backoff.
    """
    logger.info("Executing job with retry...")

    # Simulate occasional failures
    if random.random() < 0.7:  # 70% failure rate for demo
        raise TransientError("Simulated transient failure")

    return "Success after retries!"


# Job with retry on specific exceptions only
@crons.cron(
    "*/3 * * * *",
    name="filtered_retry_job",
    max_retries=3,
    retry_delay=1.0,
    retry_on=(NetworkError, TransientError),  # Only retry these
    tags=["retry", "filtered"]
)
async def job_with_filtered_retry():
    """
    Job that only retries on specific exception types.

    NetworkError and TransientError will be retried.
    PermanentError will NOT be retried.
    """
    logger.info("Executing filtered retry job...")

    # Simulate different error types
    error_type = random.choice(["network", "transient", "permanent", "success"])

    if error_type == "network":
        raise NetworkError("Connection refused")
    elif error_type == "transient":
        raise TransientError("Temporary failure")
    elif error_type == "permanent":
        raise PermanentError("This error will NOT be retried")

    return "Success!"


# =============================================================================
# CRON JOBS WITH TIMEOUT
# =============================================================================

# Job with timeout configuration
@crons.cron(
    "*/2 * * * *",
    name="job_with_timeout",
    timeout=5.0,  # 5 second timeout
    tags=["timeout"]
)
async def job_with_timeout():
    """
    Job with a 5-second timeout.

    If the job takes longer than 5 seconds, it will be cancelled
    and a JobTimeoutError will be raised.
    """
    logger.info("Starting job with 5 second timeout...")

    # Simulate variable execution time
    delay = random.uniform(1, 8)  # Sometimes exceeds timeout
    logger.info(f"  Job will take {delay:.2f} seconds...")

    await asyncio.sleep(delay)

    logger.info("Job completed within timeout!")
    return f"Completed in {delay:.2f}s"


# Job with both retry and timeout
@crons.cron(
    "*/5 * * * *",
    name="retry_with_timeout",
    max_retries=2,
    retry_delay=1.0,
    timeout=3.0,  # 3 second timeout
    tags=["retry", "timeout"]
)
async def job_with_retry_and_timeout():
    """
    Job with both retry AND timeout.

    - Timeout: 3 seconds per attempt
    - Retries: Up to 2 retries

    Note: Timeouts are NOT retried by default because they indicate
    a job that's taking too long, not a transient failure.
    """
    logger.info("Executing job with retry and timeout...")

    # Simulate work that might timeout or fail
    delay = random.uniform(1, 5)

    if delay > 3:
        logger.info(f"  This attempt will timeout ({delay:.2f}s > 3s timeout)")

    await asyncio.sleep(delay)

    # Also simulate occasional errors
    if random.random() < 0.3:
        raise TransientError("Random failure")

    return f"Completed in {delay:.2f}s"


# =============================================================================
# USING @retry_on_failure DECORATOR STANDALONE
# =============================================================================

# The retry_on_failure decorator can be used standalone for any function
@retry_on_failure(
    max_retries=3,
    retry_delay=0.5,
    backoff_multiplier=2.0,  # Double delay each retry
    max_delay=10.0,          # Cap delay at 10 seconds
    jitter=True,             # Add random jitter to prevent thundering herd
    on_retry=on_retry_callback,
)
async def fetch_data_with_retry(url: str) -> dict:
    """
    Standalone function with retry decorator.

    This can be used for any function, not just cron jobs.
    """
    logger.info(f"Fetching data from {url}...")

    # Simulate network request
    if random.random() < 0.6:
        raise NetworkError(f"Failed to connect to {url}")

    return {"url": url, "data": "sample response", "timestamp": datetime.now().isoformat()}


# Job that uses the retry-decorated function
@crons.cron("*/2 * * * *", name="fetch_job", tags=["fetch"])
async def fetch_job():
    """
    Job that calls a retry-decorated function.
    """
    try:
        result = await fetch_data_with_retry("https://api.example.com/data")
        logger.info(f"Fetch successful: {result}")
        return result
    except NetworkError as e:
        logger.error(f"All retries exhausted: {e}")
        raise


# =============================================================================
# USING execute_with_retry() DYNAMICALLY
# =============================================================================

@crons.cron("*/3 * * * *", name="dynamic_retry_job", tags=["dynamic"])
async def dynamic_retry_job():
    """
    Job demonstrating dynamic retry configuration.

    Uses execute_with_retry() for cases where you need to configure
    retry behavior at runtime.
    """
    # Create retry config dynamically
    retry_config = RetryConfig(
        max_retries=3,
        retry_delay=0.5,
        backoff_multiplier=2.0,
        max_delay=30.0,
        jitter=True,
        retry_on=(NetworkError, DatabaseError),  # Only retry these
    )

    async def unstable_operation():
        """Operation that might fail."""
        if random.random() < 0.5:
            raise random.choice([NetworkError, DatabaseError])("Random failure")
        return {"status": "ok"}

    try:
        result = await execute_with_retry(
            unstable_operation,
            retry_config,
            job_name="dynamic_operation"
        )
        logger.info(f"Dynamic retry job succeeded: {result}")
        return result
    except Exception as e:
        logger.error(f"Dynamic retry job failed: {e}")
        raise


# =============================================================================
# ERROR HANDLING HOOK for timeout
# =============================================================================

def handle_timeout_error(job_name: str, context: dict):
    """Hook to handle timeout errors specifically."""
    if context.get("is_timeout"):
        logger.critical(
            f"🚨 TIMEOUT: Job '{job_name}' exceeded its timeout. "
            f"Consider increasing timeout or optimizing the job."
        )


# Add hook to job with timeout
timeout_job = crons.get_job("job_with_timeout")
if timeout_job:
    timeout_job.add_on_error_hook(handle_timeout_error)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
def root():
    """Root endpoint with usage information."""
    return {
        "message": "FastAPI-Crons Retry and Timeout Example",
        "endpoints": {
            "/crons": "View jobs with retry/timeout config",
            "/crons/health": "Health check",
            "/test/fetch": "Test the retry-decorated fetch function",
        },
    }


@app.get("/test/fetch")
async def test_fetch():
    """Test endpoint to manually trigger the retry-decorated fetch."""
    try:
        result = await fetch_data_with_retry("https://api.test.com/endpoint")
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


# =============================================================================
# CONFIGURATION NOTES
# =============================================================================
"""
RETRY CONFIGURATION:

Via cron decorator:
    @crons.cron(
        "*/5 * * * *",
        max_retries=3,        # Number of retry attempts
        retry_delay=1.0,      # Initial delay in seconds
        retry_on=(Ex1, Ex2),  # Only retry on these exceptions
    )

Via environment variables (global defaults):
    CRON_DEFAULT_MAX_RETRIES=0       # Default: no retries
    CRON_DEFAULT_RETRY_DELAY=1.0     # Default: 1 second
    CRON_RETRY_BACKOFF_MULTIPLIER=2.0
    CRON_MAX_RETRY_DELAY=300.0       # Cap at 5 minutes

Via RetryConfig (for execute_with_retry):
    config = RetryConfig(
        max_retries=3,
        retry_delay=1.0,
        backoff_multiplier=2.0,
        max_delay=300.0,
        jitter=True,
        retry_on=(NetworkError,),
        on_retry=callback_func,
    )

TIMEOUT CONFIGURATION:

Via cron decorator:
    @crons.cron("*/5 * * * *", timeout=30.0)  # 30 second timeout

Via environment variable:
    CRON_DEFAULT_JOB_TIMEOUT=60.0  # Default 60 second timeout

Notes:
- timeout=None means use config default
- timeout=0 means no timeout (not recommended)
- Timeouts are NOT retried by default
- JobTimeoutError is raised on timeout
"""
