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

# 平台载荷中由后端根据 JWT 与请求体控制的保留字段，禁止前端通过 extra 覆盖（防越权）
RESERVED_PAYLOAD_KEYS = {
    "user_id",
    "course_id",
    "node_id",
    "global_variables",
    "messages",
    "stream",
}


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

    # JWT 登录态映射为平台全局变量 user_id/course_id/node_id。
    # user_id 按平台定义使用数值型；值为 None 的字段不下发，避免把 null 发给平台。
    global_variables: dict[str, Any] = {"user_id": user.id}
    if payload.course_id is not None:
        global_variables["course_id"] = payload.course_id
    if payload.node_id is not None:
        global_variables["node_id"] = payload.node_id

    platform_payload: dict[str, Any] = {
        "messages": messages,
        "stream": True,
        **global_variables,
        "global_variables": global_variables,
    }
    # 合并前从 extra 剥离身份/路由保留键，前端无法借 extra 冒充其他用户或篡改消息
    safe_extra = {
        key: value
        for key, value in payload.extra.items()
        if key not in RESERVED_PAYLOAD_KEYS
    }
    platform_payload.update(safe_extra)

    async def generate():
        async with httpx.AsyncClient(
            # 资源生成含多分支与反思循环，单阶段静默可能较长，read 单独放宽，避免流被提前切断
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=60.0)
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

            try:
                async for chunk in upstream.aiter_raw():
                    if chunk:
                        yield chunk
            except httpx.HTTPError as exc:
                # 流转阶段平台断连/超时不应变成 500 无声中断，统一以 SSE error 告知前端
                yield _sse_error("AgentArts 流式传输中断", str(exc))
                return

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
