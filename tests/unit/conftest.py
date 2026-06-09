"""Override MongoDB-dependent fixtures for unit tests that don't need a database."""
import asyncio
import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for async unit tests (no MongoDB needed)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def clean_test_db():
    """No-op override: unit tests don't need database cleanup."""
    # This overrides the autouse clean_test_db from tests/conftest.py
    # which requires a MongoDB connection that unit tests don't need.
    return
