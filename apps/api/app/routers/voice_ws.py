"""辅导实时语音 WS 端点（issue #21）。

/ws/tutor-voice?token=<登录JWT>&voice_session=<短时会话JWT>

消息面（JSON，音频为 hex 编码 PCM）：
  client → {type:"start_asr"} | {type:"audio", data:<hex PCM16>} |
           {type:"interrupt"} | {type:"attention_state", state:"..."} | {type:"stop"}
  server → started / asr_ready / asr_partial / asr_final / turn_start /
           assistant_final / tts_audio / turn_end / interrupted / error

辅导回答复用 TutorService（Agentic RAG + 图谱约束），attention_state 通道复用 #15。
"""

from __future__ import annotations

import binascii
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import decode_access_token
from app.db import SessionLocal
from app.llm.client import LLMClient
from app.schemas.tutor import TutorChatRequest
from app.models.user import UserRead
from app.routers.auth import current_user
from app.services.course_service import CourseService, CourseNotFoundError
from app.services.tutor_service import TutorService
from app.services.tutor_voice_service import (
    TutorVoiceSession,
    create_voice_session_token,
    decode_voice_session_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tutor-voice"])


class VoiceSessionStartPayload(BaseModel):
    course_id: int
    node_id: str = ""


class VoiceSessionStartResult(BaseModel):
    voice_session: str
    expires_in_seconds: int


@router.post("/api/tutor-voice/session", response_model=VoiceSessionStartResult)
def start_voice_session(
    payload: VoiceSessionStartPayload,
    user: UserRead = Depends(current_user),
) -> VoiceSessionStartResult:
    """签发短时语音会话 JWT（4h TTL，伯乐 _create_voice_session_id 同款）。"""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        CourseService(db).get_course(user.id, payload.course_id)
    except CourseNotFoundError:
        db.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from None
    finally:
        db.close()

    token = create_voice_session_token(user_id=user.id, course_id=payload.course_id, node_id=payload.node_id)
    return VoiceSessionStartResult(voice_session=token, expires_in_seconds=4 * 3600)

VALID_ATTENTION_STATES = {"focused", "confused", "distracted", "tired", "no_face"}


def decode_token_user_id(token: str) -> int | None:
    """登录 JWT → user_id（与 auth.current_user 同一解码规则）。"""
    try:
        payload = decode_access_token(token)
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


@router.websocket("/ws/tutor-voice")
async def tutor_voice_socket(websocket: WebSocket) -> None:
    """语音辅导 WS：登录 JWT + 短时语音会话 JWT 双重校验。"""
    token = websocket.query_params.get("token") or ""
    voice_session_token = websocket.query_params.get("voice_session") or ""
    user_id = decode_token_user_id(token)
    if not user_id:
        await websocket.close(code=4401)
        return
    try:
        claims = decode_voice_session_token(voice_session_token)
        if int(claims.get("user_id") or 0) != user_id:
            await websocket.close(code=4403)
            return
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    llm = LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        mock=settings.mock_llm,
    )
    db = SessionLocal()
    session_state = {
        "course_id": int(claims.get("course_id") or 0),
        "node_id": str(claims.get("node_id") or ""),
        "attention_state": "",
    }

    async def send_json(payload: dict) -> None:
        await websocket.send_json(payload)

    async def tutor_chat(question: str) -> str:
        response = await TutorService(CourseService(db), db=db, llm=llm).chat(
            user_id=user_id,
            request=TutorChatRequest(
                course_id=session_state["course_id"],
                message=question,
                node_id=session_state["node_id"],
                page_context="tutor-stage:realtime-voice",
                attention_state=session_state["attention_state"],
            ),
        )
        return response.answer

    import os

    session = TutorVoiceSession(
        user_id=user_id,
        send_json=send_json,
        tutor_chat=tutor_chat,
        mock_vad_seconds=float(os.getenv("VOICE_MOCK_VAD_SECONDS") or 3.0),
    )

    try:
        await session.start()
        while True:
            message = await websocket.receive_json()
            message_type = str(message.get("type") or "")
            if message_type == "start_asr":
                await session.start_asr()
            elif message_type == "audio":
                try:
                    pcm16 = binascii.unhexlify(str(message.get("data") or ""))
                except (binascii.Error, ValueError):
                    await send_json({"type": "error", "message": "音频帧编码错误"})
                    continue
                await session.feed_audio(pcm16)
            elif message_type == "attention_state":
                state = str(message.get("state") or "").strip().lower()
                if state in VALID_ATTENTION_STATES:
                    session_state["attention_state"] = state
            elif message_type == "interrupt":
                await session.interrupt()
            elif message_type == "stop":
                await session.shutdown()
                await websocket.close()
                return
    except WebSocketDisconnect:
        pass
    finally:
        await session.shutdown()
        db.close()
