"""Shared pytest configuration and fixtures for the QnA RAG test suite."""

import os

import pytest

# The application settings are instantiated at import time. Provide stable
# defaults for tests that do not care about runtime environment configuration.
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("APP_PORT", "8000")
os.environ.setdefault("APP_WORKERS", "1")


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio as the anyio backend for all async tests in this suite."""
    return "asyncio"
