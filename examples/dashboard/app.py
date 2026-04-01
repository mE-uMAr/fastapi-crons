from fastapi import FastAPI
from fastapi_crons import Crons, get_cron_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


app = FastAPI(
    title="FastAPI-Crons Dashboard Monitoring Example",
    description="Demonstrates dashboard monitoring integration",
)

# Allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    # await  some_async_function()


@crons.cron("*/5 * * * *", tags=["maintenance", "cleanup"])
async def cleanup_job():
    # This job has tags for categorization
    pass