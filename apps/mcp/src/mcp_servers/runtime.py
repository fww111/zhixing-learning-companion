"""Shared runtime helpers for the MCP servers.

This module is aligned with the Huawei Cloud AgentArts *MCP Server deployment*
contract (highcode-agentarts / agentarts_10_069 + agentarts_10_080):

* Streamable HTTP, stateless mode (``stateless_http=True``), single ``POST /mcp`` endpoint.
* ``GET /ping`` health probe for the runtime gateway.
* Tolerate the platform-injected ``Mcp-Session-Id`` header (stateless mode).
* Tolerate gateway ``Host``/``Origin`` headers: the SDK's DNS-rebinding guard only
  allows localhost by default and rejects cloud traffic (HTTP 421).
* Single-port deployment: ``PORT`` (or ``MCP_PORT``) overrides the default.
* Auth is handled by the runtime gateway in platform mode; a local bearer guard
  is opt-in via ``MCP_AUTH_MODE=local``.

References:
  https://support.huaweicloud.com/highcode-agentarts/agentarts_10_069.md
  https://support.huaweicloud.com/highcode-agentarts/agentarts_10_080.md
  https://support.huaweicloud.com/highcode-agentarts/agentarts_10_126.md
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from mcp.server import transport_security
from mcp.server.streamable_http_manager import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_servers._bootstrap import ensure_api_importable

ensure_api_importable()

from sqlalchemy.orm import Session  # noqa: E402

from app import db as app_db  # noqa: E402
from app.models.course import Course  # noqa: E402

logger = logging.getLogger("mcp_servers")

# AgentArts routes traffic through its own gateway, so the Host header seen by
# uvicorn is the runtime domain, never 127.0.0.1. The official sample patches
# this validator and disables DNS-rebinding protection for the same reason.
transport_security.TransportSecurityMiddleware._validate_host = lambda _self, _host: True  # noqa: E731

AGENTARTS_TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,
)


class CourseLookupError(RuntimeError):
    """Raised when the course does not exist or is not owned by the user."""


def ok(**data: Any) -> dict[str, Any]:
    return {"ok": True, **data}


def fail(error_type: str, message: str, **extra: Any) -> dict[str, Any]:
    logger.warning("mcp tool failure: %s: %s", error_type, message)
    return {"ok": False, "error_type": error_type, "message": message, **extra}


@contextmanager
def get_session() -> Iterator[Session]:
    session = app_db.SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_course(db: Session, user_id: int, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.user_id != user_id:
        raise CourseLookupError(f"course {course_id} not found for user {user_id}")
    return course


def iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def clamp_limit(limit: int, default: int = 50, maximum: int = 200) -> int:
    if limit is None or limit <= 0:
        return default
    return min(limit, maximum)


# ---------------------------------------------------------------------------
# ASGI application construction
# ---------------------------------------------------------------------------

_PING_FLAG = "_zhixing_ping_registered"


def register_health_route(mcp: Any) -> None:
    """Register ``GET /ping`` once (the AgentArts runtime health probe)."""
    if getattr(mcp, _PING_FLAG, False):
        return

    @mcp.custom_route("/ping", methods=["GET"])
    async def ping(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": mcp.name, "message": "pong"})

    setattr(mcp, _PING_FLAG, True)


def build_asgi_app(mcp: Any) -> Any:
    """Build the ASGI app used both by ``uvicorn`` and by local protocol tests.

    ``MCP_AUTH_MODE``:
      * ``platform`` (default): no local bearer check. The AgentArts runtime
        gateway already authenticates with its own API Key; re-checking a local
        token here would reject every platform call with 401.
      * ``local``: require ``Authorization: Bearer $MCP_ACCESS_TOKEN`` on
        ``/mcp`` calls (standalone ECS / local debugging only). ``/ping`` is
        always public so the gateway health probe is not blocked.
      * ``none``: explicitly disable all local auth.
    """
    register_health_route(mcp)
    inner = mcp.streamable_http_app()

    mode = os.getenv("MCP_AUTH_MODE", "platform").strip().lower()
    token = os.getenv("MCP_ACCESS_TOKEN", "").strip()
    if mode == "local" and not token:
        logger.warning("MCP_AUTH_MODE=local but MCP_ACCESS_TOKEN is empty; running without auth")

    if mode != "local" or not token:
        return inner

    async def guarded(scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await inner(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if path == "/ping" and method == "GET":
            await inner(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers") or []
        }
        if headers.get("authorization") != f"Bearer {token}":
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"ok":false,"error_type":"unauthorized","message":"missing or invalid bearer token"}',
                }
            )
            return
        await inner(scope, receive, send)

    return guarded


def run_server(mcp: Any, default_port: int = 8080) -> None:
    """Run a FastMCP server over stateless Streamable HTTP on a single port."""
    import uvicorn

    logging.basicConfig(level=os.getenv("MCP_LOG_LEVEL", "INFO"))

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("PORT") or os.getenv("MCP_PORT") or str(default_port))
    if os.getenv("MCP_AUTO_INIT_DB", "").lower().strip() in {"1", "true", "yes", "on"}:
        # 联调场景启动前自动建表；sqlite 联调或空库首启时无需手工建表。
        from app.db import init_db

        logger.info("MCP_AUTO_INIT_DB enabled, creating tables before serving")
        init_db()
    app = build_asgi_app(mcp)
    logger.info(
        "starting %s on %s:%s (stateless streamable-http at /mcp, health at /ping)",
        mcp.name,
        host,
        port,
    )
    uvicorn.run(app, host=host, port=port, proxy_headers=True, forwarded_allow_ips="*")
