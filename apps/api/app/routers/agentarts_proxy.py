from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.user import UserRead
from app.routers.auth import current_user


router = APIRouter(prefix="/api/agentarts", tags=["agentarts"])


class AgentArtsHistoryMessage(BaseModel):
    role: str
    content: str


class AgentArtsChatRequest(BaseModel):
    message: str
    course_id: int | None = None
    node_id: str | None = None
    history: list[AgentArtsHistoryMessage] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


def _sse_error(message: str, detail: str) -> bytes:
    payload = json.dumps(
        {"error": {"message": message, "detail": detail}},
        ensure_ascii=False,
    )
    return f"event: error\ndata: {payload}\n\n".encode("utf-8")


@router.post("/chat")
async def agentarts_chat(
    payload: AgentArtsChatRequest,
    user: UserRead = Depends(current_user),
):
    if not settings.agentarts_base_url or not settings.agentarts_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AgentArts 平台未配置：请在后端环境变量设置 AGENTARTS_BASE_URL 与 AGENTARTS_API_KEY",
        )

    messages = [{"role": m.role, "content": m.content} for m in payload.history]
    messages.append({"role": "user", "content": payload.message})

    # JWT 登录态映射为平台全局变量 user_id/course_id/node_id
    global_variables = {
        "user_id": str(user.id),
        "course_id": payload.course_id,
        "node_id": payload.node_id,
    }
    platform_payload: dict[str, Any] = {
        "messages": messages,
        "stream": True,
        **global_variables,
        "global_variables": global_variables,
    }
    platform_payload.update(payload.extra)

    async def generate():
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.agentarts_timeout_seconds, connect=10.0)
        ) as client:
            try:
                upstream = await client.send(
                    client.build_request(
                        "POST",
                        settings.agentarts_base_url,
                        headers={
                            "Authorization": f"Bearer {settings.agentarts_api_key}",
                            "Content-Type": "application/json",
                            "Accept": "text/event-stream",
                        },
                        json=platform_payload,
                    ),
                    stream=True,
                )
            except httpx.HTTPError as exc:
                yield _sse_error("连接 AgentArts 平台失败", str(exc))
                return

            if upstream.status_code >= 400:
                detail = (await upstream.aread()).decode("utf-8", errors="replace")
                yield _sse_error(f"平台返回错误 {upstream.status_code}", detail)
                return

            async for chunk in upstream.aiter_raw():
                if chunk:
                    yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
