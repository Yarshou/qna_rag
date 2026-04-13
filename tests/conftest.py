"""Shared pytest configuration and fixtures for the QnA RAG test suite."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio as the anyio backend for all async tests in this suite."""
    return "asyncio"
