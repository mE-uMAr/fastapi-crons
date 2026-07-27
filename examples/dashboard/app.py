"""Dashboard monitoring example.

Requires the optional dashboard bundle:

    pip install fastapi-crons[dashboard]

Run with ``uvicorn app:app --reload`` and open http://127.0.0.1:8000/api/dashboard
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi_crons import Crons, get_cron_router

app = FastAPI(
    title="FastAPI-Crons Dashboard Monitoring Example",
    description="Demonstrates dashboard monitoring integration",
)

# The dashboard is served from the same origin as the API, so CORS is only
# needed if you point it at a cron API running elsewhere. Narrow this to your
# real origins before deploying -- "*" plus credentials is rejected by browsers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

crons = Crons(app)

app.include_router(get_cron_router(), prefix="/api")


@crons.cron("*/5 * * * *", name="print_hello")
def print_hello():
    print("Hello! I run every 5 minutes.")


@crons.cron("0 0 * * *", name="daily_task", tags=["rewards"])
async def run_daily_task():
    # Distribute daily rewards or any async task
    print("print something")
    # await some_async_function()


@crons.cron("*/5 * * * *", tags=["maintenance", "cleanup"])
async def cleanup_job():
    # This job has tags for categorization
    pass
