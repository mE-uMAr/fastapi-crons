import os
import uuid


class CronConfig:
    """Configuration class for FastAPI Crons."""

    def __init__(self):
        # Instance identification
        self.instance_id: str = os.getenv("CRON_INSTANCE_ID", str(uuid.uuid4())[:8])

        # SQLite configuration
        self.sqlite_db_path: str = os.getenv("CRON_SQLITE_DB_PATH", "cron_state.db")

        # Redis configuration
        self.redis_url: str | None = os.getenv("CRON_REDIS_URL")
        self.redis_host: str = os.getenv("CRON_REDIS_HOST", "localhost")
        self.redis_port: int = int(os.getenv("CRON_REDIS_PORT", "6379"))
        self.redis_db: int = int(os.getenv("CRON_REDIS_DB", "0"))
        self.redis_password: str | None = os.getenv("CRON_REDIS_PASSWORD")

        # Distributed locking configuration
        self.enable_distributed_locking: bool = os.getenv("CRON_ENABLE_DISTRIBUTED_LOCKING", "false").lower() in ("true", "1", "yes")
        self.lock_ttl: int = int(os.getenv("CRON_LOCK_TTL", "300"))  # 5 minutes default

        # Logging configuration
        self.log_level: str = os.getenv("CRON_LOG_LEVEL", "INFO")
        self.enable_job_logging: bool = os.getenv("CRON_ENABLE_JOB_LOGGING", "true").lower() in ("true", "1", "yes")

        # Retry configuration - defaults for jobs that don't specify their own
        self.default_max_retries: int = int(os.getenv("CRON_DEFAULT_MAX_RETRIES", "0"))
        self.default_retry_delay: float = float(os.getenv("CRON_DEFAULT_RETRY_DELAY", "1.0"))
        self.retry_backoff_multiplier: float = float(os.getenv("CRON_RETRY_BACKOFF_MULTIPLIER", "2.0"))
        self.max_retry_delay: float = float(os.getenv("CRON_MAX_RETRY_DELAY", "300.0"))

        # Timeout configuration - default for jobs that don't specify their own
        # None means no timeout (jobs can run indefinitely)
        timeout_env = os.getenv("CRON_DEFAULT_JOB_TIMEOUT")
        self.default_job_timeout: float | None = float(timeout_env) if timeout_env else None

