import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from .config import CronConfig

logger = logging.getLogger("fastapi_cron.locking")

class LockBackend(ABC):
    """Abstract base class for lock backends."""

    @abstractmethod
    async def acquire_lock(self, key: str, ttl: int) -> str | None:
        """Acquire a lock with the given key and TTL. Returns lock ID if successful."""

    @abstractmethod
    async def release_lock(self, key: str, lock_id: str) -> bool:
        """Release a lock with the given key and lock ID."""

    @abstractmethod
    async def is_locked(self, key: str) -> bool:
        """Check if a key is currently locked."""

    @abstractmethod
    async def renew_lock(self, key: str, lock_id: str, ttl: int) -> bool:
        """Renew a lock's TTL."""

class LocalLockBackend(LockBackend):
    """Local in-memory lock backend for single-instance deployments."""

    def __init__(self) -> None:
        self.locks: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def acquire_lock(self, key: str, ttl: int) -> str | None:
        """Acquire a lock locally."""
        async with self._lock:
            now = time.time()

            # Check if lock exists and is still valid
            if key in self.locks:
                if self.locks[key]["expires_at"] > now:
                    return None  # Lock is still active
                else:
                    # Lock has expired, remove it
                    del self.locks[key]

            # Acquire new lock
            lock_id = str(uuid.uuid4())
            self.locks[key] = {
                "lock_id": lock_id,
                "expires_at": now + ttl,
                "acquired_at": now
            }

            return lock_id

    async def release_lock(self, key: str, lock_id: str) -> bool:
        """Release a lock locally."""
        async with self._lock:
            if key in self.locks and self.locks[key]["lock_id"] == lock_id:
                del self.locks[key]
                return True
            return False

    async def is_locked(self, key: str) -> bool:
        """Check if a key is locked locally."""
        async with self._lock:
            if key not in self.locks:
                return False

            now = time.time()
            if self.locks[key]["expires_at"] <= now:
                # Lock has expired, remove it
                del self.locks[key]
                return False

            return True

    async def renew_lock(self, key: str, lock_id: str, ttl: int) -> bool:
        """Renew a lock's TTL locally."""
        async with self._lock:
            if key in self.locks and self.locks[key]["lock_id"] == lock_id:
                self.locks[key]["expires_at"] = time.time() + ttl
                return True
            return False

class RedisLockBackend(LockBackend):
    """Redis-based lock backend for distributed deployments."""

    def __init__(self, redis_client: Any) -> None:
        self.redis = redis_client

    async def acquire_lock(self, key: str, ttl: int) -> str | None:
        """Acquire a distributed lock using Redis."""
        lock_id = str(uuid.uuid4())
        lock_key = f"lock:{key}"

        # Use SET with NX (only if not exists) and EX (expiration)
        result = await self.redis.set(lock_key, lock_id, nx=True, ex=ttl)

        if result:
            return lock_id
        return None

    async def release_lock(self, key: str, lock_id: str) -> bool:
        """Release a distributed lock using Redis with Lua script for atomicity."""
        lock_key = f"lock:{key}"

        # Lua script to ensure we only delete the lock if we own it
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """

        try:
            result = await self.redis.eval(lua_script, 1, lock_key, lock_id)
            return bool(result)
        except Exception as e:
            logger.error(f"Error releasing lock {key}: {e}")
            return False

    async def is_locked(self, key: str) -> bool:
        """Check if a key is locked in Redis."""
        lock_key = f"lock:{key}"
        result = await self.redis.exists(lock_key)
        return bool(result)

    async def renew_lock(self, key: str, lock_id: str, ttl: int) -> bool:
        """Renew a lock's TTL in Redis."""
        lock_key = f"lock:{key}"

        # Lua script to renew lock only if we own it
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("EXPIRE", KEYS[1], ARGV[2])
        else
            return 0
        end
        """

        try:
            result = await self.redis.eval(lua_script, 1, lock_key, lock_id, ttl)
            return bool(result)
        except Exception as e:
            logger.error(f"Error renewing lock {key}: {e}")
            return False

class DistributedLockManager:
    """Manager for distributed locking with automatic renewal."""

    def __init__(self, backend: LockBackend, config: CronConfig) -> None:
        self.backend = backend
        self.config = config
        self.active_locks: dict[str, str] = {}  # key -> lock_id
        self.renewal_task: asyncio.Task | None = None
        self._running = False

    async def acquire_lock(self, key: str) -> str | None:
        """Acquire a lock and track it for renewal."""
        lock_id = await self.backend.acquire_lock(key, self.config.lock_ttl)

        if lock_id:
            self.active_locks[key] = lock_id
            logger.debug(f"Acquired lock for {key} with ID {lock_id}")

        return lock_id

    async def release_lock(self, key: str) -> bool:
        """Release a lock and stop tracking it."""
        if key not in self.active_locks:
            return False

        lock_id = self.active_locks[key]
        success = await self.backend.release_lock(key, lock_id)

        if success:
            del self.active_locks[key]
            logger.debug(f"Released lock for {key}")

        return success

    async def is_locked(self, key: str) -> bool:
        """Check if a key is locked."""
        return await self.backend.is_locked(key)

    async def start_renewal_task(self) -> None:
        """Start the automatic lock renewal task."""
        if self._running:
            return

        self._running = True
        self.renewal_task = asyncio.create_task(self._renewal_loop())

    async def _renewal_loop(self) -> None:
        """Background task to renew active locks."""
        while self._running:
            try:
                # Renew locks at half the TTL interval
                renewal_interval = self.config.lock_ttl // 2
                await asyncio.sleep(renewal_interval)

                if not self.active_locks:
                    continue

                # Renew all active locks
                for key, lock_id in list(self.active_locks.items()):
                    try:
                        success = await self.backend.renew_lock(key, lock_id, self.config.lock_ttl)
                        if not success:
                            logger.warning(f"Failed to renew lock for {key}, removing from active locks")
                            self.active_locks.pop(key, None)
                        else:
                            logger.debug(f"Renewed lock for {key}")
                    except Exception as e:
                        logger.error(f"Error renewing lock for {key}: {e}")
                        self.active_locks.pop(key, None)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in lock renewal loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    async def cleanup(self) -> None:
        """Clean up the lock manager."""
        self._running = False

        if self.renewal_task and not self.renewal_task.done():
            self.renewal_task.cancel()
            try:
                await self.renewal_task
            except asyncio.CancelledError:
                pass

        # Release all active locks
        for key in list(self.active_locks.keys()):
            await self.release_lock(key)
