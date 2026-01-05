"""
Distributed Locking Example for FastAPI-Crons

This example demonstrates:
- Redis-based distributed locking for multi-instance deployments
- Preventing duplicate job execution across instances
- Lock configuration and fallback behavior

Requirements:
    pip install fastapi-crons redis
    docker run -d -p 6379:6379 redis:alpine

Run multiple instances:
    uvicorn app:app --port 8001 &
    uvicorn app:app --port 8002 &

Observe that jobs only run on ONE instance at a time.
"""

import asyncio
import logging
import os
import socket
from datetime import datetime

from fastapi import FastAPI

from fastapi_crons import (
    CronConfig,
    Crons,
    SQLiteStateBackend,
    get_cron_router,
    log_job_start,
    log_job_success,
)
from fastapi_crons.locking import (
    DistributedLockManager,
    LocalLockBackend,
    RedisLockBackend,
)

# Try to import redis
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None


# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Get unique instance ID (defaults to hostname + port for uniqueness)
INSTANCE_ID = os.getenv(
    "CRON_INSTANCE_ID",
    f"{socket.gethostname()}-{os.getpid()}"
)

# Redis configuration
REDIS_URL = os.getenv("CRON_REDIS_URL", "redis://localhost:6379/0")
ENABLE_DISTRIBUTED_LOCKING = os.getenv("CRON_ENABLE_DISTRIBUTED_LOCKING", "true").lower() == "true"


# =============================================================================
# APP SETUP with Distributed Locking
# =============================================================================

app = FastAPI(
    title="FastAPI-Crons Distributed Locking Example",
    description=f"Instance ID: {INSTANCE_ID}",
)


def create_crons_with_locking() -> Crons:
    """
    Create Crons instance with optional distributed locking.

    This demonstrates how to:
    1. Check for Redis availability
    2. Create Redis-based lock backend
    3. Fall back to local locking if Redis is unavailable
    """
    # Create configuration
    config = CronConfig()
    config.instance_id = INSTANCE_ID
    config.enable_distributed_locking = ENABLE_DISTRIBUTED_LOCKING

    # Create state backend (SQLite for persistence)
    state_backend = SQLiteStateBackend(db_path="cron_state.db")

    # Create lock manager
    lock_manager = None

    if ENABLE_DISTRIBUTED_LOCKING and REDIS_AVAILABLE:
        try:
            # Create Redis client
            redis_client = redis.from_url(REDIS_URL)

            # Create Redis lock backend
            lock_backend = RedisLockBackend(
                redis_client,
                key_prefix="cron_lock:",  # Prefix for lock keys
            )

            # Create lock manager with Redis backend
            lock_manager = DistributedLockManager(lock_backend, config)

            logger.info(f"✅ Distributed locking enabled with Redis at {REDIS_URL}")

        except Exception as e:
            logger.warning(f"⚠️ Failed to connect to Redis: {e}")
            logger.warning("   Falling back to local locking")

    if lock_manager is None:
        # Fallback to local locking (single-instance only)
        lock_backend = LocalLockBackend()
        lock_manager = DistributedLockManager(lock_backend, config)
        logger.info("[INFO] Using local locking (single-instance mode)")

    # Create Crons instance with configured components
    crons = Crons(
        app=app,
        state_backend=state_backend,
        lock_manager=lock_manager,
        config=config,
    )

    return crons


# Initialize crons with distributed locking
crons = create_crons_with_locking()
app.include_router(get_cron_router(), prefix="/crons", tags=["Cron Jobs"])


# =============================================================================
# CRON JOBS (Only one instance runs each job)
# =============================================================================

@crons.cron("*/1 * * * *", name="exclusive_job", tags=["distributed"])
async def exclusive_job():
    """
    Job that runs exclusively on one instance.

    When distributed locking is enabled:
    - The first instance to acquire the lock runs the job
    - Other instances skip the job and wait for next schedule
    - The lock is released after job completion

    This prevents duplicate execution in multi-instance deployments.
    """
    logger.info(f"🔒 Exclusive job running on instance: {INSTANCE_ID}")

    # Simulate some work
    await asyncio.sleep(5)

    logger.info(f"🔓 Exclusive job completed on instance: {INSTANCE_ID}")
    return {"instance": INSTANCE_ID, "timestamp": datetime.now().isoformat()}


# Attach logging hooks
exclusive = crons.get_job("exclusive_job")
if exclusive:
    exclusive.add_before_run_hook(log_job_start)
    exclusive.add_after_run_hook(log_job_success)


@crons.cron("*/2 * * * *", name="long_running_job", tags=["distributed", "long"])
async def long_running_job():
    """
    Long-running job demonstrating lock TTL.

    The lock has a TTL (time-to-live) to prevent deadlocks:
    - If an instance crashes while holding a lock, the lock expires
    - The lock is automatically renewed during job execution
    - Default TTL is 5 minutes (configurable via CRON_LOCK_TTL)
    """
    logger.info(f"⏳ Long-running job started on {INSTANCE_ID}")

    # Simulate long work
    for i in range(6):
        logger.info(f"   Progress: {i+1}/6")
        await asyncio.sleep(10)

    logger.info(f"✅ Long-running job completed on {INSTANCE_ID}")
    return "completed"


@crons.cron("0 * * * *", name="hourly_synchronized_job", tags=["distributed", "hourly"])
def hourly_synchronized_job():
    """
    Hourly job that runs on exactly one instance.

    Perfect for:
    - Database migrations
    - Report generation
    - Cache warming
    - Cleanup tasks

    These tasks should only run once, not on every instance.
    """
    logger.info(f"📊 Hourly synchronized job running on {INSTANCE_ID}")

    # Example: Generate a report
    report = {
        "generated_by": INSTANCE_ID,
        "generated_at": datetime.now().isoformat(),
        "data": "Sample report data",
    }

    logger.info(f"📊 Report generated: {report}")
    return report


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
def root():
    """Root endpoint with instance information."""
    return {
        "message": "FastAPI-Crons Distributed Locking Example",
        "instance_id": INSTANCE_ID,
        "distributed_locking": ENABLE_DISTRIBUTED_LOCKING,
        "redis_available": REDIS_AVAILABLE,
        "endpoints": {
            "/crons": "View registered jobs",
            "/crons/health": "Health check",
            "/instance": "Instance details",
            "/lock-status/{job_name}": "Check if a job is currently locked",
        },
    }


@app.get("/instance")
def get_instance_info():
    """Get information about this instance."""
    return {
        "instance_id": INSTANCE_ID,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "distributed_locking_enabled": ENABLE_DISTRIBUTED_LOCKING,
        "lock_backend": type(crons.lock_manager.backend).__name__,
    }


@app.get("/lock-status/{job_name}")
async def get_lock_status(job_name: str):
    """Check if a job is currently locked."""
    lock_key = f"job:{job_name}"
    is_locked = await crons.lock_manager.is_locked(lock_key)

    return {
        "job_name": job_name,
        "lock_key": lock_key,
        "is_locked": is_locked,
        "message": "Job is currently running on another instance" if is_locked else "Job is available",
    }


# =============================================================================
# CONFIGURATION NOTES
# =============================================================================
"""
DISTRIBUTED LOCKING CONFIGURATION:

Environment Variables:
    CRON_INSTANCE_ID=my-instance-1     # Unique instance identifier
    CRON_ENABLE_DISTRIBUTED_LOCKING=true
    CRON_REDIS_URL=redis://localhost:6379/0
    CRON_REDIS_HOST=localhost          # Alternative to URL
    CRON_REDIS_PORT=6379
    CRON_REDIS_DB=0
    CRON_REDIS_PASSWORD=secret
    CRON_LOCK_TTL=300                  # Lock TTL in seconds (5 min default)

Programmatic Configuration:
    from fastapi_crons import Crons, CronConfig
    from fastapi_crons.locking import DistributedLockManager, RedisLockBackend
    import redis.asyncio as redis

    config = CronConfig()
    config.instance_id = "my-instance"
    config.enable_distributed_locking = True
    config.lock_ttl = 300

    redis_client = redis.from_url("redis://localhost:6379")
    lock_backend = RedisLockBackend(redis_client)
    lock_manager = DistributedLockManager(lock_backend, config)

    crons = Crons(app=app, lock_manager=lock_manager, config=config)

DEPLOYMENT NOTES:

1. All instances must connect to the SAME Redis server
2. Each instance needs a UNIQUE instance_id
3. The lock TTL should be longer than your longest job
4. Locks are automatically renewed during execution
5. If an instance crashes, locks expire after TTL
6. SQLite state can be shared via network filesystem or use Redis state backend
"""
