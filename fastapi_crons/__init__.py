__version__ = "2.0.1"

from .config import CronConfig
from .endpoints import get_cron_router
from .hooks import (
    alert_on_failure,
    alert_on_long_duration,
    log_job_error,
    log_job_start,
    log_job_success,
    metrics_collector,
    webhook_notification,
)
from .job import CronJob, cron_job
from .locking import DistributedLockManager, LocalLockBackend, RedisLockBackend
from .retry import RetryConfig, execute_with_retry, retry_on_failure
from .runner import JobTimeoutError
from .scheduler import Crons
from .state import RedisStateBackend, SQLiteStateBackend

# Optional OpenTelemetry integration
try:
    from .telemetry import OpenTelemetryHooks, is_otel_available
except ImportError:
    OpenTelemetryHooks = None  # type: ignore
    is_otel_available = lambda: False  # noqa: E731

__all__ = [
    "CronConfig",
    "CronJob",
    "Crons",
    "DistributedLockManager",
    "JobTimeoutError",
    "LocalLockBackend",
    "OpenTelemetryHooks",
    "RedisLockBackend",
    "RedisStateBackend",
    "RetryConfig",
    "SQLiteStateBackend",
    "__version__",
    "alert_on_failure",
    "alert_on_long_duration",
    "cron_job",
    "execute_with_retry",
    "get_cron_router",
    "is_otel_available",
    "log_job_error",
    "log_job_start",
    "log_job_success",
    "metrics_collector",
    "retry_on_failure",
    "webhook_notification",
]

