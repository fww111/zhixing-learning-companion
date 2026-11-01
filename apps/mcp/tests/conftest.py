"""Test setup: force a sqlite database BEFORE any app.* import happens."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DIR = tempfile.mkdtemp(prefix="zhixing-mcp-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(_TMP_DIR) / 'test.db').as_posix()}"
os.environ.setdefault("MOCK_LLM", "true")

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    from app.db import init_db

    init_db()
    yield
