"""Pytest configuration and shared fixtures for fastapi-crons tests."""
import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi_crons import Crons, CronConfig, SQLiteStateBackend
from fastapi_crons.locking import LocalLockBackend, DistributedLockManager


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


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
    crons = Crons(
        app=fastapi_app,
        state_backend=sqlite_backend,
        lock_manager=lock_manager,
        config=cron_config
    )
    return crons
