"""Shared runtime helpers for the three MCP servers."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from mcp_servers._bootstrap import ensure_api_importable

ensure_api_importable()

from sqlalchemy.orm import Session  # noqa: E402

from app import db as app_db  # noqa: E402
from app.models.course import Course  # noqa: E402

logger = logging.getLogger("mcp_servers")


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


def run_server(mcp: Any, default_port: int) -> None:
    """Run a FastMCP server over streamable HTTP with optional bearer auth."""
    import uvicorn

    logging.basicConfig(level=os.getenv("MCP_LOG_LEVEL", "INFO"))

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", str(default_port)))
    if os.getenv("MCP_AUTO_INIT_DB", "").lower().strip() in {"1", "true", "yes", "on"}:
        # 联调场景启动前自动建表；容器内三个进程会并发执行 init_db，
        # MySQL 下并发 create_all 可能触发 1050 already exists 竞态，
        # 表已存在即可继续，故对"already exists"做容错忽略。
        from app.db import init_db

        logger.info("MCP_AUTO_INIT_DB enabled, creating tables before serving")
        try:
            init_db()
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "already exists" in msg.lower() or "1050" in msg:
                logger.warning("tables already exist (concurrent init), continuing: %s", msg)
            else:
                raise
    app = build_asgi_app(mcp)
    logger.info("starting %s on %s:%s (streamable-http at /mcp)", mcp.name, host, port)
    uvicorn.run(app, host=host, port=port)


def build_asgi_app(mcp: Any) -> Any:
    # 本地联调/内网隧道场景：FastMCP 默认 host=127.0.0.1 会启用 DNS rebinding 保护，
    # 拒绝 trycloudflare.com 等隧道 Host（421 Invalid Host header）。
    # 仅作为开发联调开关，生产部署（ECS/公网域名）不应全局关闭。
    transport_security = getattr(mcp.settings, "transport_security", None)
    if transport_security is None or transport_security.enable_dns_rebinding_protection:
        try:
            from mcp.server.transport_security import TransportSecuritySettings

            mcp.settings.transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=False,
                allowed_hosts=[],
                allowed_origins=[],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not disable DNS rebinding protection: %s", exc)

    inner = mcp.streamable_http_app()
    token = os.getenv("MCP_ACCESS_TOKEN", "").strip()

    if not token:
        return inner

    async def guarded(scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await inner(scope, receive, send)
            return
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers") or []}
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
