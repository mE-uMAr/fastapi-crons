"""
Health Monitoring Example for FastAPI-Crons

This example demonstrates:
- Using the built-in /health endpoint for monitoring
- Kubernetes liveness/readiness probe configuration
- Prometheus metrics integration concepts
- Custom health check logic

Run with:
    uvicorn app:app --reload

Then visit:
    - http://localhost:8000/crons/health - Built-in health check
    - http://localhost:8000/health/detailed - Custom detailed health
    - http://localhost:8000/health/kubernetes - Kubernetes probe format
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Response

from fastapi_crons import (
    Crons,
    get_cron_router,
    log_job_error,
    log_job_start,
    log_job_success,
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
    title="FastAPI-Crons Health Monitoring Example",
    description="Demonstrates health check endpoint and monitoring integration",
)

crons = Crons(app)

# Include the cron router with health endpoint
# The router provides /health, /system/status, and job management endpoints
app.include_router(get_cron_router(), prefix="/crons", tags=["Cron Jobs"])


# =============================================================================
# CUSTOM HEALTH TRACKING
# =============================================================================

class HealthTracker:
    """
    Custom health tracker for detailed monitoring.

    Tracks job execution history for health assessment.
    """

    def __init__(self, window_minutes: int = 60):
        self.window_minutes = window_minutes
        self.job_history: list[dict] = []
        self.start_time = time.time()

    def record_execution(self, job_name: str, success: bool, duration: float):
        """Record a job execution."""
        self.job_history.append({
            "job_name": job_name,
            "success": success,
            "duration": duration,
            "timestamp": datetime.now(timezone.utc),
        })

        # Clean old entries
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.window_minutes)
        self.job_history = [
            e for e in self.job_history
            if e["timestamp"] > cutoff
        ]

    def get_stats(self) -> dict:
        """Get health statistics."""
        if not self.job_history:
            return {
                "total_executions": 0,
                "success_rate": 1.0,
                "avg_duration": 0,
                "failures_last_hour": 0,
            }

        total = len(self.job_history)
        successes = sum(1 for e in self.job_history if e["success"])
        failures = total - successes
        avg_duration = sum(e["duration"] for e in self.job_history) / total

        return {
            "total_executions": total,
            "success_rate": successes / total if total > 0 else 1.0,
            "avg_duration": round(avg_duration, 3),
            "failures_last_hour": failures,
        }

    def get_uptime(self) -> float:
        """Get uptime in seconds."""
        return time.time() - self.start_time


# Create global health tracker
health_tracker = HealthTracker()


# =============================================================================
# HEALTH TRACKING HOOKS
# =============================================================================

def track_success(job_name: str, context: dict):
    """Hook to track successful job execution."""
    health_tracker.record_execution(
        job_name,
        success=True,
        duration=context.get("duration", 0),
    )


def track_failure(job_name: str, context: dict):
    """Hook to track failed job execution."""
    health_tracker.record_execution(
        job_name,
        success=False,
        duration=context.get("duration", 0),
    )


# =============================================================================
# CRON JOBS
# =============================================================================

@crons.cron("*/1 * * * *", name="healthy_job", tags=["monitored"])
async def healthy_job():
    """
    Job that usually succeeds.
    """
    logger.info("Executing healthy job...")
    await asyncio.sleep(random.uniform(0.1, 0.5))
    return "success"


@crons.cron("*/2 * * * *", name="flaky_job", tags=["monitored", "flaky"])
async def flaky_job():
    """
    Job that occasionally fails for health monitoring demo.
    """
    logger.info("Executing flaky job...")
    await asyncio.sleep(random.uniform(0.2, 0.8))

    if random.random() < 0.2:  # 20% failure rate
        raise ValueError("Random failure")

    return "success"


@crons.cron("*/5 * * * *", name="health_check_job", tags=["meta"])
async def self_health_check():
    """
    Meta job that checks system health.

    This job can:
    - Send health status to external monitoring
    - Clean up stale data
    - Trigger alerts if degraded
    """
    stats = health_tracker.get_stats()

    if stats["success_rate"] < 0.8:
        logger.warning(f"⚠️ System degraded: success rate = {stats['success_rate']:.1%}")
    else:
        logger.info(f"✓ System healthy: success rate = {stats['success_rate']:.1%}")

    return stats


# Add tracking hooks to all jobs
for job in crons.get_jobs():
    job.add_before_run_hook(log_job_start)
    job.add_after_run_hook(log_job_success)
    job.add_after_run_hook(track_success)
    job.add_on_error_hook(log_job_error)
    job.add_on_error_hook(track_failure)


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================

@app.get("/")
def root():
    """Root endpoint with health endpoint links."""
    return {
        "message": "FastAPI-Crons Health Monitoring Example",
        "health_endpoints": {
            "/crons/health": "Built-in health check (JSON)",
            "/health/detailed": "Detailed health with history",
            "/health/kubernetes": "Kubernetes liveness probe",
            "/health/readiness": "Kubernetes readiness probe",
            "/metrics/prometheus": "Prometheus-style metrics",
        },
    }


@app.get("/health/detailed")
async def detailed_health():
    """
    Detailed health check with execution history.

    Provides more information than the built-in endpoint.
    """
    jobs = crons.get_jobs()
    backend = crons.state_backend

    job_statuses = []
    for job in jobs:
        status = await backend.get_job_status(job.name)
        job_statuses.append({
            "name": job.name,
            "tags": job.tags,
            "next_run": job.next_run.isoformat(),
            "status": status.get("status") if status else "unknown",
        })

    stats = health_tracker.get_stats()

    # Determine health status
    if stats["success_rate"] < 0.5:
        status = "unhealthy"
    elif stats["success_rate"] < 0.9:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "uptime_seconds": round(health_tracker.get_uptime(), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "jobs": job_statuses,
    }


@app.get("/health/kubernetes")
async def kubernetes_liveness(response: Response):
    """
    Kubernetes liveness probe endpoint.

    Returns 200 if the service is alive, 503 otherwise.
    Use this for Kubernetes livenessProbe.

    livenessProbe:
      httpGet:
        path: /health/kubernetes
        port: 8000
      initialDelaySeconds: 10
      periodSeconds: 10
    """
    stats = health_tracker.get_stats()
    uptime = health_tracker.get_uptime()

    # Consider unhealthy if success rate is very low
    is_healthy = stats["success_rate"] >= 0.3 or stats["total_executions"] < 5

    if not is_healthy:
        response.status_code = 503
        return {"status": "unhealthy", "reason": "Low success rate"}

    return {
        "status": "healthy",
        "uptime": round(uptime, 2),
    }


@app.get("/health/readiness")
async def kubernetes_readiness(response: Response):
    """
    Kubernetes readiness probe endpoint.

    Returns 200 if the service is ready to receive traffic.
    Use this for Kubernetes readinessProbe.

    readinessProbe:
      httpGet:
        path: /health/readiness
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 5
    """
    # Check if we can access the state backend
    try:
        jobs = crons.get_jobs()
        if jobs:
            await crons.state_backend.get_job_status(jobs[0].name)
        is_ready = True
    except Exception:
        is_ready = False

    if not is_ready:
        response.status_code = 503
        return {"ready": False, "reason": "Backend unavailable"}

    return {"ready": True, "jobs": len(crons.get_jobs())}


@app.get("/metrics/prometheus")
async def prometheus_metrics():
    """
    Prometheus-style metrics endpoint.

    Returns metrics in Prometheus exposition format.

    For production, consider using prometheus-client library:
        pip install prometheus-client

    scrape_configs:
      - job_name: 'fastapi-crons'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: /metrics/prometheus
    """
    stats = health_tracker.get_stats()
    jobs = crons.get_jobs()

    # Build Prometheus metrics format
    lines = [
        "# HELP cron_uptime_seconds Uptime in seconds",
        "# TYPE cron_uptime_seconds gauge",
        f'cron_uptime_seconds {health_tracker.get_uptime():.2f}',
        "",
        "# HELP cron_jobs_total Total number of registered jobs",
        "# TYPE cron_jobs_total gauge",
        f'cron_jobs_total {len(jobs)}',
        "",
        "# HELP cron_executions_total Total job executions in last hour",
        "# TYPE cron_executions_total counter",
        f'cron_executions_total {stats["total_executions"]}',
        "",
        "# HELP cron_success_rate Job success rate",
        "# TYPE cron_success_rate gauge",
        f'cron_success_rate {stats["success_rate"]:.4f}',
        "",
        "# HELP cron_failures_total Job failures in last hour",
        "# TYPE cron_failures_total counter",
        f'cron_failures_total {stats["failures_last_hour"]}',
        "",
        "# HELP cron_avg_duration_seconds Average job duration",
        "# TYPE cron_avg_duration_seconds gauge",
        f'cron_avg_duration_seconds {stats["avg_duration"]:.4f}',
    ]

    return Response(content="\n".join(lines), media_type="text/plain")


# =============================================================================
# CONFIGURATION NOTES
# =============================================================================
"""
BUILT-IN HEALTH ENDPOINT (/crons/health):

Returns:
{
    "status": "healthy" | "degraded" | "unhealthy",
    "version": "2.0.1",
    "uptime_seconds": 123.45,
    "timestamp": "2024-01-01T00:00:00Z",
    "instance_id": "abc123",
    "jobs": {
        "total": 5,
        "running": 1,
        "completed": 3,
        "failed": 1
    },
    "backend": {
        "type": "SQLiteStateBackend",
        "connected": true
    },
    "config": {
        "distributed_locking": false,
        "default_timeout": null,
        "default_max_retries": 0
    }
}

STATUS MEANINGS:
- healthy: All systems operational, no failed jobs
- degraded: System working but some jobs failed
- unhealthy: Critical issues (e.g., backend disconnected)

KUBERNETES PROBE CONFIGURATION:

spec:
  containers:
  - name: app
    livenessProbe:
      httpGet:
        path: /health/kubernetes
        port: 8000
      initialDelaySeconds: 10
      periodSeconds: 10
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /health/readiness
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 5
      failureThreshold: 3

DOCKER HEALTHCHECK:

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/crons/health || exit 1
"""
