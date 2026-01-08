"""Pytest configuration and shared fixtures for fastapi-crons tests."""
import gc
import os
import tempfile
import time

import pytest
from fastapi import FastAPI

import fastapi_crons.scheduler as scheduler_module
from fastapi_crons import CronConfig, Crons, SQLiteStateBackend
from fastapi_crons.locking import DistributedLockManager, LocalLockBackend


def reset_global_crons():
    """Reset the global crons instance to ensure test isolation."""
    scheduler_module._global_crons = None


def _safe_remove_file(path: str, retries: int = 3, delay: float = 0.1) -> None:
    """Safely remove a file with retry logic for Windows file locking issues."""
    for i in range(retries):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except PermissionError:
            if i < retries - 1:
                gc.collect()  # Force garbage collection to release file handles
                time.sleep(delay)
            # Ignore on last retry - CI cleanup will handle it


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup with retry for Windows
    _safe_remove_file(db_path)


@pytest.fixture
async def sqlite_backend(temp_db):
    """Create a SQLite state backend with temporary database."""
    backend = SQLiteStateBackend(db_path=temp_db)
    yield backend
    # Close the connection to release the file lock
    await backend.close()


@pytest.fixture
def cron_config():
    """Create a test CronConfig."""
    config = CronConfig()
    config.enable_distributed_locking = False
    return config


@pytest.fixture
def lock_manager(cron_config):
    """Create a local lock manager for testing."""
    lock_backend = LocalLockBackend()
    return DistributedLockManager(lock_backend, cron_config)


@pytest.fixture
async def crons_instance(sqlite_backend, lock_manager, cron_config):
    """Create a Crons instance for testing."""
    # Reset global state to ensure test isolation
    reset_global_crons()
    crons = Crons(
        state_backend=sqlite_backend,
        lock_manager=lock_manager,
        config=cron_config
    )
    return crons


@pytest.fixture
def fastapi_app():
    """Create a FastAPI app for testing."""
    return FastAPI()


@pytest.fixture
async def crons_with_app(fastapi_app, sqlite_backend, lock_manager, cron_config):
    """Create a Crons instance integrated with FastAPI app."""
    # Reset global state to ensure test isolation
    reset_global_crons()
    crons = Crons(
        app=fastapi_app,
        state_backend=sqlite_backend,
        lock_manager=lock_manager,
        config=cron_config
    )
    return crons
