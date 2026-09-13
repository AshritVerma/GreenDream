"""Test environment: no network, no key, its own data directory.

The environment is set before `app` is imported, because `config.settings` reads it once at
import. Every test starts from these defaults via the autouse fixture.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="greendream-llm-tests-"))

os.environ.update({
    "GD_DATA_DIR": str(TMP),
    "GD_OFFLINE": "1",          # no outbound requests at all
    "GD_GATE": "open",
    "GD_RATE_SECONDS": "0",
    "GD_RATE_PER_HOUR": "0",
    "GD_ADMIN_TOKEN": "test-admin",
    "GD_INGEST_TOKEN": "",
    "GD_LIVE_VIEW_URL": "https://example.test/live",
    "ANTHROPIC_API_KEY": "",
    "ANTHROPIC_MODEL": "claude-haiku-4-5",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    settings.refresh()
    ratelimit.reset()
    yield
    settings.refresh()
    ratelimit.reset()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
