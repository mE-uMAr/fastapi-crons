from typing import Callable, Optional, List, Any, Union, Awaitable
from datetime import datetime
from croniter import croniter

# Type for hook functions - can be sync or async
HookFunc = Union[
    Callable[[str, dict], None],  # Sync hook
    Callable[[str, dict], Awaitable[None]]  # Async hook
]

class CronJob:
    def __init__(self, func: Callable, expr: str, name: Optional[str] = None, tags: Optional[List[str]] = None) -> None:
        self.func = func
        self.expr = expr
        self.name = name or func.__name__
        self.tags = tags or []
        self._cron_iter = croniter(expr, datetime.now())
        self.last_run: Optional[datetime] = None
        self.next_run: datetime = self._cron_iter.get_next(datetime)
        
        # Hooks for job execution
        self.before_run_hooks: List[HookFunc] = []
        self.after_run_hooks: List[HookFunc] = []
        self.on_error_hooks: List[HookFunc] = []

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

def cron_job(expr: str, *, name: Optional[str] = None, tags: Optional[List[str]] = None) -> Callable:
    """Decorator for creating a cron job."""
    from .scheduler import Crons
    
    def wrapper(func: Callable) -> Callable:
        # Get or create the global Crons instance
        crons = Crons()
        job = CronJob(func, expr, name=name, tags=tags)
        crons.jobs.append(job)
        return func
    
    return wrapper
