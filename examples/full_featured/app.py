"""
Full-Featured Example for FastAPI-Crons

This example demonstrates ALL features combined:
- Basic cron job scheduling (sync and async)
- Job tags for organization
- Custom hooks (before, after, error)
- Built-in hooks (logging, metrics, alerts)
- Retry decorator with exponential backoff
- Job timeout configuration
- Health check endpoint
- OpenTelemetry integration (optional)
- Distributed locking (with Redis, optional)

This is a complete, production-ready example.

Run with:
    uvicorn app:app --reload

Then visit:
    - http://localhost:8000/           - API overview
    - http://localhost:8000/crons      - View all jobs
    - http://localhost:8000/crons/health - Health check
    - http://localhost:8000/metrics    - Metrics overview
"""

import asyncio
import logging
import os
import random
import socket
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

from fastapi_crons import (
    CronConfig,
    # Core
    Crons,
    # Retry
    SQLiteStateBackend,
    alert_on_failure,
    alert_on_long_duration,
    get_cron_router,
    # Telemetry
    is_otel_available,
    log_job_error,
    # Hooks
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
# CONFIGURATION
# =============================================================================

# Instance identification (important for distributed locking)
INSTANCE_ID = os.getenv("CRON_INSTANCE_ID", f"{socket.gethostname()}-{os.getpid()}")

# Feature flags (controlled via environment)
ENABLE_DISTRIBUTED_LOCKING = os.getenv("CRON_ENABLE_DISTRIBUTED_LOCKING", "false").lower() == "true"
ENABLE_OTEL = os.getenv("ENABLE_OTEL", "false").lower() == "true" and is_otel_available()

# Default retry/timeout settings
DEFAULT_MAX_RETRIES = int(os.getenv("CRON_DEFAULT_MAX_RETRIES", "2"))
DEFAULT_TIMEOUT = float(os.getenv("CRON_DEFAULT_JOB_TIMEOUT", "60"))


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    title="FastAPI-Crons Full-Featured Example",
    description=f"Production-ready cron scheduling (Instance: {INSTANCE_ID})",
    version="1.0.0",
)


def create_crons() -> Crons:
    """Create and configure the Crons scheduler."""

    # Create configuration
    config = CronConfig()
    config.instance_id = INSTANCE_ID
    config.enable_distributed_locking = ENABLE_DISTRIBUTED_LOCKING
    config.default_max_retries = DEFAULT_MAX_RETRIES
    config.default_job_timeout = DEFAULT_TIMEOUT

    # Create state backend
    state_backend = SQLiteStateBackend(db_path="cron_state.db")

    # Create Crons instance
    crons = Crons(
        app=app,
        state_backend=state_backend,
        config=config,
    )

    return crons


crons = create_crons()


# Include the cron router
app.include_router(get_cron_router(), prefix="/crons", tags=["Cron Jobs"])


# =============================================================================
# OPENTELEMETRY SETUP (Optional)
# =============================================================================

otel_hooks = None

if ENABLE_OTEL and is_otel_available():
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        from fastapi_crons.telemetry import OpenTelemetryHooks

        # Setup OpenTelemetry
        resource = Resource.create({"service.name": "fastapi-crons-fullexample"})
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

        # Create hooks
        otel_hooks = OpenTelemetryHooks(service_name="fastapi-crons-fullexample")
        logger.info("✅ OpenTelemetry enabled")
    except Exception as e:
        logger.warning(f"⚠️ Could not setup OpenTelemetry: {e}")


# =============================================================================
# CUSTOM HOOKS
# =============================================================================

def business_metric_hook(job_name: str, context: dict[str, Any]):
    """
    Custom hook for recording business metrics.

    In production, you might:
    - Send to Datadog/NewRelic
    - Record in a time-series database
    - Update business dashboards
    """
    duration = context.get("duration", 0)
    success = context.get("success", False)

    # Record in metrics collector
    if success:
        logger.info(f"📊 Business metric: {job_name} completed in {duration:.2f}s")
    else:
        logger.error(f"📊 Business metric: {job_name} FAILED after {duration:.2f}s")


async def slack_notification_hook(job_name: str, context: dict[str, Any]):
    """
    Async hook for sending Slack notifications on failure.

    In production, replace with actual Slack webhook call.
    """
    error = context.get("error", "Unknown error")

    # Simulate sending Slack notification
    logger.warning(
        f"🔔 [SLACK] Job '{job_name}' failed: {error}\n"
        f"   Instance: {context.get('instance_id')}\n"
        f"   Duration: {context.get('duration', 0):.2f}s"
    )
    await asyncio.sleep(0.1)  # Simulate network call


# =============================================================================
# GLOBAL HOOKS (Applied to all jobs)
# =============================================================================

# Add logging hooks to all jobs
crons.add_before_run_hook(log_job_start)
crons.add_after_run_hook(log_job_success)
crons.add_after_run_hook(business_metric_hook)
crons.add_on_error_hook(log_job_error)
crons.add_on_error_hook(slack_notification_hook)

# Add metrics collection
crons.add_before_run_hook(metrics_collector.record_job_start)
crons.add_after_run_hook(metrics_collector.record_job_success)
crons.add_on_error_hook(metrics_collector.record_job_failure)

# Add OpenTelemetry hooks if enabled
if otel_hooks:
    crons.add_before_run_hook(otel_hooks.before_run)
    crons.add_after_run_hook(otel_hooks.after_run)
    crons.add_on_error_hook(otel_hooks.on_error)


# =============================================================================
# CRON JOBS - Various Patterns
# =============================================================================

# -----------------------------------------------------------------------------
# 1. Simple job with minimal configuration
# -----------------------------------------------------------------------------
@crons.cron("*/1 * * * *", name="heartbeat")
def heartbeat():
    """
    Simple heartbeat job running every minute.

    Use for:
    - Keeping connections alive
    - Simple health checks
    - Metrics heartbeat
    """
    logger.info(f"💓 Heartbeat from {INSTANCE_ID}")
    return {"instance": INSTANCE_ID, "timestamp": datetime.now(timezone.utc).isoformat()}


# -----------------------------------------------------------------------------
# 2. Async job with retry and timeout
# -----------------------------------------------------------------------------
@crons.cron(
    "*/2 * * * *",
    name="data_sync",
    tags=["sync", "critical"],
    max_retries=3,
    retry_delay=5.0,
    timeout=30.0,
)
async def data_sync_job():
    """
    Data synchronization job with retry and timeout.

    Use for:
    - Syncing data from external APIs
    - Database replication
    - Cache warming
    """
    logger.info("🔄 Starting data sync...")

    # Simulate API call that might fail
    if random.random() < 0.2:  # 20% failure rate
        raise ConnectionError("External API unavailable")

    await asyncio.sleep(random.uniform(1, 5))

    records_synced = random.randint(100, 1000)
    logger.info(f"🔄 Synced {records_synced} records")

    return {"records_synced": records_synced}


# -----------------------------------------------------------------------------
# 3. Maintenance job with long duration alert
# -----------------------------------------------------------------------------
@crons.cron(
    "0 * * * *",  # Every hour
    name="cleanup_old_data",
    tags=["maintenance", "database"],
    timeout=300.0,  # 5 minute timeout
)
async def cleanup_job():
    """
    Hourly cleanup job with long duration alerting.

    Use for:
    - Purging old records
    - Cleaning temporary files
    - Archiving logs
    """
    logger.info("🧹 Starting cleanup...")

    # Simulate cleanup work
    await asyncio.sleep(random.uniform(2, 10))

    deleted = random.randint(50, 500)
    logger.info(f"🧹 Deleted {deleted} old records")

    return {"deleted": deleted}


# Add long duration alert (triggers if job takes > 60 seconds)
cleanup = crons.get_job("cleanup_old_data")
if cleanup:
    cleanup.add_after_run_hook(alert_on_long_duration(threshold_seconds=60.0))
    cleanup.add_on_error_hook(alert_on_failure)


# -----------------------------------------------------------------------------
# 4. Report generation job (daily)
# -----------------------------------------------------------------------------
@crons.cron(
    "0 0 * * *",  # Daily at midnight
    name="daily_report",
    tags=["reports", "scheduled"],
    max_retries=2,
    timeout=600.0,  # 10 minute timeout for report generation
)
async def generate_daily_report():
    """
    Daily report generation job.

    Use for:
    - Business intelligence reports
    - Email summaries
    - Analytics aggregation
    """
    logger.info("📊 Generating daily report...")

    # Simulate report generation
    await asyncio.sleep(random.uniform(5, 15))

    report = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "metrics": {
            "users": random.randint(1000, 5000),
            "revenue": random.uniform(10000, 50000),
            "orders": random.randint(100, 500),
        },
    }

    logger.info(f"📊 Daily report generated: {report}")
    return report


# -----------------------------------------------------------------------------
# 5. Job with retry on specific exceptions only
# -----------------------------------------------------------------------------
class DatabaseError(Exception):
    pass

class NetworkError(Exception):
    pass


@crons.cron(
    "*/5 * * * *",
    name="external_api_job",
    tags=["api", "external"],
    max_retries=3,
    retry_delay=10.0,
    retry_on=(NetworkError, ConnectionError),  # Only retry these
    timeout=60.0,
)
async def external_api_job():
    """
    Job that calls external API with selective retry.

    Only retries on network-related errors, not on validation errors.
    """
    logger.info("🌐 Calling external API...")

    await asyncio.sleep(random.uniform(0.5, 2))

    # Simulate different error types
    error_type = random.choice(["success", "success", "network", "database"])

    if error_type == "network":
        raise NetworkError("Connection timed out")
    elif error_type == "database":
        raise DatabaseError("Invalid data format")  # This won't be retried

    return {"api_response": "OK"}


# -----------------------------------------------------------------------------
# 6. Webhook notification job
# -----------------------------------------------------------------------------
@crons.cron(
    "*/10 * * * *",
    name="send_webhooks",
    tags=["notifications", "webhooks"],
    max_retries=5,
    retry_delay=30.0,
    timeout=120.0,
)
async def send_pending_webhooks():
    """
    Process and send pending webhook notifications.

    High retry count for reliable delivery.
    """
    logger.info("📤 Processing pending webhooks...")

    # Simulate processing webhooks
    pending = random.randint(0, 20)
    sent = 0

    for _i in range(pending):
        await asyncio.sleep(0.1)  # Simulate sending
        if random.random() > 0.05:  # 95% success rate
            sent += 1

    logger.info(f"📤 Sent {sent}/{pending} webhooks")
    return {"pending": pending, "sent": sent, "failed": pending - sent}


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
def root():
    """API overview with all endpoints."""
    return {
        "service": "FastAPI-Crons Full Example",
        "instance_id": INSTANCE_ID,
        "features": {
            "distributed_locking": ENABLE_DISTRIBUTED_LOCKING,
            "opentelemetry": ENABLE_OTEL,
            "default_retries": DEFAULT_MAX_RETRIES,
            "default_timeout": DEFAULT_TIMEOUT,
        },
        "endpoints": {
            "/crons": "List all jobs with status",
            "/crons/health": "Health check",
            "/crons/{name}": "Get job details",
            "/crons/{name}/run": "Manually trigger job (POST)",
            "/metrics": "View collected metrics",
            "/jobs/summary": "Quick job summary",
        },
    }


@app.get("/metrics")
def get_metrics():
    """Get all collected metrics."""
    return {
        "collector": "MetricsCollector",
        "all_metrics": metrics_collector.get_metrics(),
        "per_job": {
            job.name: metrics_collector.get_job_metrics(job.name)
            for job in crons.get_jobs()
        },
    }


@app.get("/jobs/summary")
def jobs_summary():
    """Quick summary of all jobs."""
    jobs = crons.get_jobs()
    return {
        "total": len(jobs),
        "jobs": [
            {
                "name": j.name,
                "expr": j.expr,
                "tags": j.tags,
                "next_run": j.next_run.isoformat(),
                "retries": j.max_retries,
                "timeout": j.timeout,
            }
            for j in jobs
        ],
    }


# =============================================================================
# PRODUCTION NOTES
# =============================================================================
"""
PRODUCTION DEPLOYMENT CHECKLIST:

1. ENVIRONMENT VARIABLES:
   CRON_INSTANCE_ID=unique-id-per-instance
   CRON_ENABLE_DISTRIBUTED_LOCKING=true
   CRON_REDIS_URL=redis://redis:6379/0
   CRON_DEFAULT_MAX_RETRIES=3
   CRON_DEFAULT_JOB_TIMEOUT=300
   CRON_LOG_LEVEL=INFO

2. REDIS FOR DISTRIBUTED LOCKING:
   - Required for multi-instance deployments
   - Prevents duplicate job execution
   - Use Redis Cluster for high availability

3. MONITORING:
   - Use /crons/health for liveness probes
   - Integrate with Prometheus via metrics endpoint
   - Set up alerts for degraded status

4. OPENTELEMETRY:
   - Enable with ENABLE_OTEL=true
   - Configure OTLP exporter for production
   - Send traces to Jaeger/Tempo/etc.

5. ERROR HANDLING:
   - Configure Sentry or similar for error tracking
   - Set up Slack/PagerDuty webhooks for critical failures

6. DATABASE:
   - For production, consider RedisStateBackend
   - Or use shared SQLite on network filesystem
   - Ensure proper backup of state database

DOCKER COMPOSE EXAMPLE:

version: '3.8'
services:
  cron-worker-1:
    build: .
    environment:
      - CRON_INSTANCE_ID=worker-1
      - CRON_ENABLE_DISTRIBUTED_LOCKING=true
      - CRON_REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis

  cron-worker-2:
    build: .
    environment:
      - CRON_INSTANCE_ID=worker-2
      - CRON_ENABLE_DISTRIBUTED_LOCKING=true
      - CRON_REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
"""
