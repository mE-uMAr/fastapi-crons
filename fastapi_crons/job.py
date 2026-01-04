from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from croniter import croniter

# Type for hook functions - can be sync or async
HookFunc = (
    Callable[[str, dict], None] |  # Sync hook
    Callable[[str, dict], Awaitable[None]]  # Async hook
)

class CronJob:
    def __init__(
        self,
        func: Callable,
        expr: str,
        name: str | None = None,
        tags: list[str] | None = None,
        max_retries: int | None = None,
        retry_delay: float | None = None,
        retry_on: tuple[type[Exception], ...] | None = None,
        timeout: float | None = None,
    ) -> None:
        self.func = func
        self.expr = expr
        self.name = name or func.__name__
        self.tags = tags or []
        self._cron_iter = croniter(expr, datetime.now(timezone.utc))
        self.last_run: datetime | None = None
        self.next_run: datetime = self._cron_iter.get_next(datetime)

        # Retry configuration (None means use defaults from CronConfig)
        self.max_retries: int | None = max_retries
        self.retry_delay: float | None = retry_delay
        self.retry_on: tuple[type[Exception], ...] | None = retry_on

        # Timeout configuration (None means use default from CronConfig, 0 means no timeout)
        self.timeout: float | None = timeout

        # Hooks for job execution
        self.before_run_hooks: list[HookFunc] = []
        self.after_run_hooks: list[HookFunc] = []
        self.on_error_hooks: list[HookFunc] = []

    def update_next_run(self) -> None:
        self.next_run = self._cron_iter.get_next(datetime)

    def add_before_run_hook(self, hook: HookFunc) -> "CronJob":
        """Add a hook to be executed before the job runs."""
        self.before_run_hooks.append(hook)
        return self  # For method chaining

    def add_after_run_hook(self, hook: HookFunc) -> "CronJob":
        """Add a hook to be executed after the job runs successfully."""
        self.after_run_hooks.append(hook)
        return self  # For method chaining

    def add_on_error_hook(self, hook: HookFunc) -> "CronJob":
        """Add a hook to be executed when the job fails."""
        self.on_error_hooks.append(hook)
        return self  # For method chaining

def cron_job(
    expr: str,
    *,
    name: str | None = None,
    tags: list[str] | None = None,
    max_retries: int | None = None,
    retry_delay: float | None = None,
    retry_on: tuple[type[Exception], ...] | None = None,
    timeout: float | None = None,
) -> Callable:
    """Decorator for creating a cron job with optional retry and timeout configuration."""
    from .scheduler import Crons

    def wrapper(func: Callable) -> Callable:
        # Get or create the global Crons instance
        crons = Crons()
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
        crons.jobs.append(job)
        return func

    return wrapper

