"""Shared pytest configuration and fixtures for the QnA RAG test suite."""

import os
from pathlib import Path

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


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-tag tests with ``unit``/``integration`` markers based on their directory.

    Tests under ``tests/unit`` are tagged ``unit`` and tests under
    ``tests/integration`` are tagged ``integration`` so that CI can filter
    with ``pytest -m unit`` / ``pytest -m integration`` without requiring
    every author to add the decorator manually.  Tests already marked with
    ``llm`` keep that marker — a provider-backed test is still an
    integration test, but the ``llm`` marker is the stronger signal for CI.
    """
    unit_dir = Path("tests") / "unit"
    integration_dir = Path("tests") / "integration"
    for item in items:
        path = Path(str(item.path))
        if unit_dir in path.parents or any(part == "unit" for part in path.parts):
            item.add_marker(pytest.mark.unit)
        elif integration_dir in path.parents or any(part == "integration" for part in path.parts):
            item.add_marker(pytest.mark.integration)
