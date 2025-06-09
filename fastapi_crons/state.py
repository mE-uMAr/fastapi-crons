import aiosqlite
import asyncio
from datetime import datetime
from typing import Optional, List, Tuple
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger("fastapi_cron.state")

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

class StateBackend(ABC):
    """Abstract base class for state backends."""
    
    @abstractmethod
    async def set_last_run(self, job_name: str, timestamp: datetime):
        """Set the last run timestamp for a job."""
        pass
    
    @abstractmethod
    async def get_last_run(self, job_name: str) -> Optional[str]:
        """Get the last run timestamp for a job."""
        pass
    
    @abstractmethod
    async def get_all_jobs(self) -> List[Tuple[str, Optional[str]]]:
        """Get all jobs and their last run timestamps."""
        pass
    
    @abstractmethod
    async def set_job_status(self, job_name: str, status: str, instance_id: str):
        """Set the status of a job (running, completed, failed)."""
        pass
    
    @abstractmethod
    async def get_job_status(self, job_name: str) -> Optional[dict]:
        """Get the status of a job."""
        pass

class SQLiteStateBackend(StateBackend):
    """SQLite-based state backend with thread safety."""
    
    def __init__(self, db_path: str = "cron_state.db"):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    async def _ensure_tables(self, db):
        """Ensure required tables exist."""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS job_state (
                name TEXT PRIMARY KEY,
                last_run TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS job_status (
                name TEXT PRIMARY KEY,
                status TEXT,
                instance_id TEXT,
                started_at TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS job_execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT,
                instance_id TEXT,
                status TEXT,
                started_at TEXT,
                completed_at TEXT,
                duration REAL,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

    async def set_last_run(self, job_name: str, timestamp: datetime):
        """Set the last run timestamp for a job with thread safety."""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                await db.execute(
                    """INSERT OR REPLACE INTO job_state (name, last_run, updated_at) 
                       VALUES (?, ?, ?)""",
                    (job_name, timestamp.isoformat(), datetime.now().isoformat())
                )
                await db.commit()

    async def get_last_run(self, job_name: str) -> Optional[str]:
        """Get the last run timestamp for a job."""
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT last_run FROM job_state WHERE name=?", (job_name,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def get_all_jobs(self) -> List[Tuple[str, Optional[str]]]:
        """Get all jobs and their last run timestamps."""
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT name, last_run FROM job_state ORDER BY name") as cursor:
                return await cursor.fetchall()
    
    async def set_job_status(self, job_name: str, status: str, instance_id: str):
        """Set the status of a job."""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                now = datetime.now().isoformat()
                
                if status == "running":
                    await db.execute(
                        """INSERT OR REPLACE INTO job_status 
                           (name, status, instance_id, started_at, updated_at) 
                           VALUES (?, ?, ?, ?, ?)""",
                        (job_name, status, instance_id, now, now)
                    )
                else:
                    await db.execute(
                        """UPDATE job_status 
                           SET status = ?, updated_at = ? 
                           WHERE name = ? AND instance_id = ?""",
                        (status, now, job_name, instance_id)
                    )
                
                await db.commit()
    
    async def get_job_status(self, job_name: str) -> Optional[dict]:
        """Get the status of a job."""
        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_tables(db)
            async with db.execute(
                "SELECT status, instance_id, started_at, updated_at FROM job_status WHERE name=?", 
                (job_name,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "status": row[0],
                        "instance_id": row[1],
                        "started_at": row[2],
                        "updated_at": row[3]
                    }
                return None
    
    async def log_job_execution(self, job_name: str, instance_id: str, status: str, 
                               started_at: datetime, completed_at: Optional[datetime] = None,
                               duration: Optional[float] = None, error_message: Optional[str] = None):
        """Log job execution details."""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_tables(db)
                await db.execute(
                    """INSERT INTO job_execution_log 
                       (job_name, instance_id, status, started_at, completed_at, duration, error_message)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (job_name, instance_id, status, started_at.isoformat(),
                     completed_at.isoformat() if completed_at else None,
                     duration, error_message)
                )
                await db.commit()

class RedisStateBackend(StateBackend):
    """Redis-based state backend for distributed deployments."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def set_last_run(self, job_name: str, timestamp: datetime):
        """Set the last run timestamp for a job."""
        key = f"cron:job:{job_name}:last_run"
        await self.redis.set(key, timestamp.isoformat())
    
    async def get_last_run(self, job_name: str) -> Optional[str]:
        """Get the last run timestamp for a job."""
        key = f"cron:job:{job_name}:last_run"
        result = await self.redis.get(key)
        return result.decode() if result else None
    
    async def get_all_jobs(self) -> List[Tuple[str, Optional[str]]]:
        """Get all jobs and their last run timestamps."""
        pattern = "cron:job:*:last_run"
        keys = await self.redis.keys(pattern)
        
        jobs = []
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            job_name = key_str.split(":")[2]  # Extract job name from key
            last_run = await self.redis.get(key)
            last_run_str = last_run.decode() if last_run else None
            jobs.append((job_name, last_run_str))
        
        return sorted(jobs)
    
    async def set_job_status(self, job_name: str, status: str, instance_id: str):
        """Set the status of a job."""
        key = f"cron:job:{job_name}:status"
        status_data = {
            "status": status,
            "instance_id": instance_id,
            "updated_at": datetime.now().isoformat()
        }
        
        if status == "running":
            status_data["started_at"] = datetime.now().isoformat()
        
        await self.redis.hset(key, mapping=status_data)
        
        # Set expiration for status (cleanup old statuses)
        await self.redis.expire(key, 3600)  # 1 hour
    
    async def get_job_status(self, job_name: str) -> Optional[dict]:
        """Get the status of a job."""
        key = f"cron:job:{job_name}:status"
        result = await self.redis.hgetall(key)
        
        if result:
            return {k.decode(): v.decode() for k, v in result.items()}
        return None
