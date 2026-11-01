"""Make the FastAPI codebase (apps/api/app) importable from the MCP servers.

The MCP layer intentionally reuses the API's SQLAlchemy models and services as
the single source of truth; this shim only wires up the import path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3] / "api"


def ensure_api_importable() -> None:
    if str(_API_ROOT) not in sys.path:
        sys.path.insert(0, str(_API_ROOT))
