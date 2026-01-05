"""
Basic Usage Example for FastAPI-Crons

This example demonstrates the fundamental usage of fastapi-crons:
- Setting up the Crons scheduler with FastAPI
- Defining sync and async cron jobs with decorators
- Using job tags for organization
- Accessing the monitoring endpoint

Run with:
    uvicorn app:app --reload

Then visit:
    - http://localhost:8000/       - Root endpoint
    - http://localhost:8000/crons  - View all registered jobs
    - http://localhost:8000/crons/health - Health check
"""

from datetime import datetime

from fastapi import FastAPI

# Import the core components from fastapi-crons
from fastapi_crons import Crons, get_cron_router

# =============================================================================
# APP SETUP
# =============================================================================

# Create FastAPI application
app = FastAPI(
    title="FastAPI-Crons Basic Example",
    description="Demonstrates basic cron job scheduling",
)

# Initialize the cron scheduler with the app
# This automatically starts/stops cron jobs with the app lifecycle
crons = Crons(app)

# Include the cron management router
# This provides endpoints like /crons, /crons/{job_name}, /crons/{job_name}/run
app.include_router(get_cron_router(), prefix="/crons", tags=["Cron Jobs"])


# =============================================================================
# CRON JOBS
# =============================================================================

# Simple sync job running every minute
# The job name defaults to the function name if not specified
@crons.cron("* * * * *")
def simple_sync_job():
    """
    A simple synchronous cron job that runs every minute.

    Cron Expression: * * * * *
    ┌───────────── minute (0-59) - every minute (*)
    │ ┌───────────── hour (0-23) - every hour (*)
    │ │ ┌───────────── day of month (1-31) - every day (*)
    │ │ │ ┌───────────── month (1-12) - every month (*)
    │ │ │ │ ┌───────────── day of week (0-6, Sun-Sat) - every day (*)
    │ │ │ │ │
    * * * * *
    """
    print(f"[{datetime.now()}] Simple sync job executed!")


# Async job running every 5 minutes with a custom name
@crons.cron("*/5 * * * *", name="async_every_5_min")
async def async_periodic_job():
    """
    An async cron job that runs every 5 minutes.

    Use async jobs when you need to:
    - Make HTTP requests
    - Query databases
    - Perform I/O operations
    """
    import asyncio

    print(f"[{datetime.now()}] Starting async job...")

    # Simulate async work (e.g., API call, database query)
    await asyncio.sleep(1)

    print(f"[{datetime.now()}] Async job completed!")

    return {"status": "success", "timestamp": datetime.now().isoformat()}


# Job with tags for organization
@crons.cron("0 * * * *", name="hourly_cleanup", tags=["maintenance", "cleanup"])
async def hourly_cleanup():
    """
    A maintenance job that runs at the start of every hour.

    Tags help you organize and filter jobs:
    - maintenance: System maintenance tasks
    - cleanup: Cleanup and housekeeping

    Cron Expression: 0 * * * *
    - Runs at minute 0 of every hour
    """
    print(f"[{datetime.now()}] Running hourly cleanup...")

    # Example cleanup operations:
    # - Clear temporary files
    # - Purge old cache entries
    # - Archive old logs

    return "Cleanup completed"


# Daily job example
@crons.cron("0 0 * * *", name="daily_report", tags=["reports", "daily"])
async def generate_daily_report():
    """
    A job that runs daily at midnight.

    Cron Expression: 0 0 * * *
    - Runs at 00:00 (midnight) every day
    """
    print(f"[{datetime.now()}] Generating daily report...")

    # Example report generation:
    # - Aggregate daily statistics
    # - Generate PDF/Excel reports
    # - Send email summaries

    return "Daily report generated"


# Weekly job example
@crons.cron("0 0 * * 0", name="weekly_backup", tags=["backup", "weekly"])
def weekly_backup():
    """
    A job that runs weekly on Sunday at midnight.

    Cron Expression: 0 0 * * 0
    - Runs at 00:00 every Sunday (0 = Sunday)
    """
    print(f"[{datetime.now()}] Running weekly backup...")

    # Example backup operations:
    # - Database backup
    # - File system snapshots
    # - Offsite replication

    return "Backup completed"


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
def root():
    """Root endpoint with usage information."""
    return {
        "message": "FastAPI-Crons Basic Example",
        "endpoints": {
            "/crons": "View all registered cron jobs",
            "/crons/health": "Health check endpoint",
            "/crons/{job_name}": "Get details for a specific job",
            "/crons/{job_name}/run": "Manually trigger a job (POST)",
        },
        "registered_jobs": len(crons.get_jobs()),
    }


@app.get("/jobs/summary")
async def jobs_summary():
    """Get a summary of all registered jobs."""
    jobs = crons.get_jobs()

    return {
        "total_jobs": len(jobs),
        "jobs": [
            {
                "name": job.name,
                "expression": job.expr,
                "tags": job.tags,
                "next_run": job.next_run.isoformat(),
            }
            for job in jobs
        ],
    }


# =============================================================================
# USAGE NOTES
# =============================================================================
"""
CRON EXPRESSION CHEAT SHEET:

┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of the month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of the week (0 - 6) (Sunday to Saturday)
│ │ │ │ │
* * * * *

Common patterns:
- * * * * *     : Every minute
- */5 * * * *   : Every 5 minutes
- 0 * * * *     : Every hour (at minute 0)
- 0 0 * * *     : Daily at midnight
- 0 0 * * 0     : Weekly on Sunday at midnight
- 0 0 1 * *     : Monthly on the 1st at midnight
- 0 0 1 1 *     : Yearly on January 1st at midnight

Special values:
- *      : Any value
- */n    : Every n units
- n-m    : Range from n to m
- n,m    : List of n and m
"""
