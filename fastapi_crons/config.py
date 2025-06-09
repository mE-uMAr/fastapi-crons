import os
import uuid
from typing import Optional

class CronConfig:
    """Configuration class for FastAPI Crons."""
    
    def __init__(self):
        # Instance identification
        self.instance_id: str = os.getenv("CRON_INSTANCE_ID", str(uuid.uuid4())[:8])
        
        # SQLite configuration
        self.sqlite_db_path: str = os.getenv("CRON_SQLITE_DB_PATH", "cron_state.db")
        
        # Redis configuration
        self.redis_url: Optional[str] = os.getenv("CRON_REDIS_URL")
        self.redis_host: str = os.getenv("CRON_REDIS_HOST", "localhost")
        self.redis_port: int = int(os.getenv("CRON_REDIS_PORT", "6379"))
        self.redis_db: int = int(os.getenv("CRON_REDIS_DB", "0"))
        self.redis_password: Optional[str] = os.getenv("CRON_REDIS_PASSWORD")
        
        # Distributed locking configuration
        self.enable_distributed_locking: bool = os.getenv("CRON_ENABLE_DISTRIBUTED_LOCKING", "false").lower() in ("true", "1", "yes")
        self.lock_ttl: int = int(os.getenv("CRON_LOCK_TTL", "300"))  # 5 minutes default
        
        # Logging configuration
        self.log_level: str = os.getenv("CRON_LOG_LEVEL", "INFO")
        self.enable_job_logging: bool = os.getenv("CRON_ENABLE_JOB_LOGGING", "true").lower() in ("true", "1", "yes")
