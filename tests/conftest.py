"""Pytest configuration and shared fixtures for fastapi-crons tests."""
import asyncio
import os
import sys
import tempfile

import pytest
from fastapi import FastAPI

import fastapi_crons.scheduler as scheduler_module
from fastapi_crons import CronConfig, Crons, SQLiteStateBackend
from fastapi_crons.locking import DistributedLockManager, LocalLockBackend

# Windows requires WindowsSelectorEventLoopPolicy for compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def reset_global_crons():
    """Reset the global crons instance to ensure test isolation."""
    scheduler_module._global_crons = None


@pytest.fixture(scope="session")
def event_loop_policy():
    """Configure event loop policy for cross-platform compatibility."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def sqlite_backend(temp_db):
    """Create a SQLite state backend with temporary database."""
    return SQLiteStateBackend(db_path=temp_db)


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
def crons_instance(sqlite_backend, lock_manager, cron_config):
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
def crons_with_app(fastapi_app, sqlite_backend, lock_manager, cron_config):
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
