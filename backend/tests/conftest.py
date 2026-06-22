from __future__ import annotations

import os

# Disable the APScheduler background thread for the entire test suite.
# Must be set BEFORE app.main is imported so the first get_settings() call
# (which is lru_cached) reads enable_hold_scheduler=False.
os.environ.setdefault("ENABLE_HOLD_SCHEDULER", "false")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
