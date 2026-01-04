import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, Optional

from .config import CronConfig
from .job import CronJob, HookFunc
from .locking import DistributedLockManager, LocalLockBackend
from .runner import run_job_loop
from .state import SQLiteStateBackend, StateBackend

try:
    import redis.asyncio as redis

    from .locking import RedisLockBackend
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

logger = logging.getLogger(__name__)

# Global instance to share jobs across decorators and scheduler
_global_crons: Optional["Crons"] = None

class Crons:
    def __init__(self, app: Any | None = None, state_backend: StateBackend | None = None,
                 lock_manager: DistributedLockManager | None = None,
                 config: CronConfig | None = None) -> None:
        global _global_crons

        self.jobs: list[CronJob] = []
        self.config = config or CronConfig()
        self.state_backend = state_backend or SQLiteStateBackend(self.config.sqlite_db_path)
        self.lock_manager = lock_manager
        self.app = app
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._startup_delay = 2.0  # Delay to allow job registration

        # Initialize lock manager if not provided
        if self.lock_manager is None:
            if self.config.enable_distributed_locking and REDIS_AVAILABLE:
                try:
                    redis_client = redis.from_url(self.config.redis_url) if self.config.redis_url else redis.Redis(
                        host=self.config.redis_host,
                        port=self.config.redis_port,
                        db=self.config.redis_db,
                        password=self.config.redis_password
                    )
                    lock_backend = RedisLockBackend(redis_client)
                    self.lock_manager = DistributedLockManager(lock_backend, self.config)
                except Exception as e:
                    logger.warning(f"Failed to initialize Redis lock backend: {e}")
                    lock_backend = LocalLockBackend()
                    self.lock_manager = DistributedLockManager(lock_backend, self.config)
            else:
                lock_backend = LocalLockBackend()
                self.lock_manager = DistributedLockManager(lock_backend, self.config)

        # If there's a global instance, inherit its jobs (copy to avoid shared mutation)
        if _global_crons and _global_crons != self:
            self.jobs = list(_global_crons.jobs)

        # Set as global instance
        _global_crons = self

        if app:
            self.init_app(app)

    def init_app(self, app: Any) -> None:
        """Initialize with FastAPI app - automatically start/stop with app lifecycle."""

        # Check if app already has a lifespan
        existing_lifespan = getattr(app.router, 'lifespan_context', None)

        @asynccontextmanager
        async def lifespan_with_crons(app: Any):  # type: ignore
            # Startup - delay to allow job registration
            await asyncio.sleep(self._startup_delay)
            await self.start()
            try:
                if existing_lifespan:
                    # If there's an existing lifespan, run it
                    async with existing_lifespan(app):
                        yield
                else:
                    yield
            finally:
                # Shutdown
                await self.stop()

        # Set the new lifespan
        app.router.lifespan_context = lifespan_with_crons

    async def start(self) -> None:
        """Start the cron scheduler."""
        if self._running:
            return

        self._running = True

        # Wait a bit more to ensure all jobs are registered
        if not self.jobs:
            logger.info("No jobs found, waiting for job registration...")
            for _ in range(10):  # Wait up to 5 more seconds
                await asyncio.sleep(0.5)
                if self.jobs:
                    break

        logger.info(f"Starting cron scheduler with {len(self.jobs)} jobs")

        if not self.jobs:
            logger.warning("No cron jobs registered!")
            return

        # Start lock manager renewal task
        await self.lock_manager.start_renewal_task()

        # Start job loops
        for job in self.jobs:
            logger.info(f"Starting job loop for '{job.name}' with expression '{job.expr}'")
            task = asyncio.create_task(
                run_job_loop(job, self.state_backend, self.lock_manager, self.config)
            )
            self._tasks.append(task)

    async def stop(self) -> None:
        """Stop the cron scheduler."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping cron scheduler")

        # Cancel all job tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

        # Stop lock manager
        await self.lock_manager.cleanup()

    def cron(
        self,
        expr: str,
        *,
        name: str | None = None,
        tags: list[str] | None = None,
        max_retries: int | None = None,
        retry_delay: float | None = None,
        retry_on: tuple[type[Exception], ...] | None = None,
        timeout: float | None = None,
    ) -> Callable:
        """Decorator for creating cron jobs with optional retry and timeout configuration.

        Args:
            expr: Cron expression (e.g., "*/5 * * * *" for every 5 minutes)
            name: Job name (defaults to function name)
            tags: List of tags for categorization
            max_retries: Maximum retry attempts on failure (None = use config default)
            retry_delay: Initial delay between retries in seconds (None = use config default)
            retry_on: Tuple of exception types to retry on (None = retry on all exceptions)
            timeout: Job timeout in seconds (None = use config default, 0 = no timeout)
        """
        def wrapper(func: Callable) -> Callable:
            job = CronJob(
                func,
                expr,
                name=name,
                tags=tags,
                max_retries=max_retries,
                retry_delay=retry_delay,
                retry_on=retry_on,
                timeout=timeout,
            )
            self.jobs.append(job)
            logger.info(f"Registered cron job '{job.name}' with expression '{expr}'")

            # If scheduler is already running, start this job immediately
            if self._running:
                logger.info(f"Scheduler already running, starting job '{job.name}' immediately")
                task = asyncio.create_task(
                    run_job_loop(job, self.state_backend, self.lock_manager, self.config)
                )
                self._tasks.append(task)

            return func
        return wrapper

    def get_jobs(self) -> list[CronJob]:
        return self.jobs

    def get_job(self, name: str) -> CronJob | None:
        """Get a job by name."""
        for job in self.jobs:
            if job.name == name:
                return job
        return None

    def add_before_run_hook(self, hook: HookFunc, job_name: str | None = None) -> "Crons":
        """Add a hook to be executed before job runs."""
        if job_name:
            job = self.get_job(job_name)
            if job:
                job.add_before_run_hook(hook)
        else:
            for job in self.jobs:
                job.add_before_run_hook(hook)
        return self

    def add_after_run_hook(self, hook: HookFunc, job_name: str | None = None) -> "Crons":
        """Add a hook to be executed after job runs successfully."""
        if job_name:
            job = self.get_job(job_name)
            if job:
                job.add_after_run_hook(hook)
        else:
            for job in self.jobs:
                job.add_after_run_hook(hook)
        return self

    def add_on_error_hook(self, hook: HookFunc, job_name: str | None = None) -> "Crons":
        """Add a hook to be executed when job fails."""
        if job_name:
            job = self.get_job(job_name)
            if job:
                job.add_on_error_hook(hook)
        else:
            for job in self.jobs:
                job.add_on_error_hook(hook)
        return self

# Convenience function to get the global crons instance
def get_crons() -> Crons:
    """Get the global crons instance, creating one if it doesn't exist."""
    global _global_crons
    if _global_crons is None:
        _global_crons = Crons()
    return _global_crons
