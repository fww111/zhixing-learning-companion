"""Edge TTS：真人神经网络音色语音合成（供对话大屏朗读讲题内容）。

免费无需账号；音色列表见 edge_tts 文档，常用中文音色：
- zh-CN-XiaoxiaoNeural（女，自然亲切）
- zh-CN-YunxiNeural（男，阳光）
音色通过环境变量 TTS_EDGE_VOICE 配置。
"""

from __future__ import annotations

import os

import edge_tts
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.models.user import UserRead
from app.routers.auth import current_user

router = APIRouter(prefix="/api/tts", tags=["tts"])

DEFAULT_VOICE = os.getenv("TTS_EDGE_VOICE", "zh-CN-XiaoxiaoNeural")
# 微软 TTS 端点（speech.platform.bing.com）网络受限时经由本地代理出网；
# 留空则直连。可用 TTS_EDGE_PROXY 或标准 HTTPS_PROXY 配置。
TTS_EDGE_PROXY = os.getenv("TTS_EDGE_PROXY") or os.getenv("HTTPS_PROXY") or ""


class EdgeTtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str | None = None


@router.post("/speak")
async def speak(
    payload: EdgeTtsRequest,
    user: UserRead = Depends(current_user),
) -> Response:
    """文本转真人音色语音（mp3）。用于对话大屏朗读 AI 讲题内容。"""
    voice = (payload.voice or DEFAULT_VOICE).strip()
    try:
        communicate = edge_tts.Communicate(payload.text, voice, proxy=TTS_EDGE_PROXY or None)
        audio_bytes = b"".join([chunk async for chunk in communicate.stream() if isinstance(chunk, bytes)])
    except Exception as exc:  # noqa: BLE001 — TTS 失败不应 500 阻塞前端，返回 502 由前端降级
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"TTS 合成失败：{exc}",
        ) from exc

    if not audio_bytes:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="TTS 合成结果为空")

    return Response(content=audio_bytes, media_type="audio/mpeg")
