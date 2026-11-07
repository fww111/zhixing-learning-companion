"""辅导实时语音会话编排（issue #21）。

一条 WS 连接内的轮次生命周期：
  上行 PCM16 → Fun-ASR（3s 静音 VAD 断句）→ asr_final
  → 打断当前播报（伯乐 _interrupt_current_turn 模式）
  → TutorService.chat（Agentic RAG + attention_state）
  → 句级切分（。！？;；\n）逐句送豆包双向 TTS
  → PCM24k 音频帧下行至前端无缝排队播放

会话安全：语音会话 id 为短时 JWT（4h TTL，session_type=tutor_voice，
伯乐 _create_voice_session_id 同款），WS 握手另验登录 JWT。
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.security import create_access_token, decode_access_token
from app.services.voice_providers import (
    ASRProvider,
    TTSSession,
    build_asr_provider,
    build_tts_session,
    voice_providers_ready,
)

logger = logging.getLogger(__name__)

VOICE_SESSION_TOKEN_TTL_SECONDS = 4 * 3600

# 句级切分：中文句末 + 分号 + 换行；再对超长句按逗号二次切分（≤120 字）
SENTENCE_BREAK_PATTERN = re.compile(r"(?<=[。！？!?；;\n])")
COMMA_SPLIT_PATTERN = re.compile(r"(?<=[，,、])")
MAX_SENTENCE_CHARS = 120


@dataclass
class TutorVoiceTurnState:
    turn_id: str = ""
    asr_text: str = ""
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


def create_voice_session_token(*, user_id: int, course_id: int, node_id: str = "") -> str:
    """短时语音会话 JWT（伯乐 _create_voice_session_id 同款，4h TTL 独立于登录态）。"""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=VOICE_SESSION_TOKEN_TTL_SECONDS)
    return create_access_token(
        str(user_id),
        {
            "session_type": "tutor_voice",
            "voice_session_id": str(uuid.uuid4()),
            "user_id": user_id,
            "course_id": course_id,
            "node_id": node_id,
            # extra 后合并，覆盖默认的登录态过期时间 → 独立 4h 会话 TTL
            "exp": expires_at,
        },
    )


def decode_voice_session_token(token: str) -> dict[str, Any]:
    payload = decode_access_token(token)
    if payload.get("session_type") != "tutor_voice":
        raise ValueError("无效的语音会话标识")
    return payload


def split_sentences(text: str) -> list[str]:
    """句级切分：先按句末标点，超长句再按逗号二次切分。

    TTS 边生成边出声的关键：不等整段回答，切出第一句即开始合成。
    """
    normalized = (text or "").strip()
    if not normalized:
        return []
    raw_sentences = [s.strip() for s in SENTENCE_BREAK_PATTERN.split(normalized) if s.strip()]
    sentences: list[str] = []
    for sentence in raw_sentences:
        if len(sentence) <= MAX_SENTENCE_CHARS:
            sentences.append(sentence)
            continue
        chunk = ""
        for piece in COMMA_SPLIT_PATTERN.split(sentence):
            piece = piece.strip()
            if not piece:
                continue
            if len(chunk) + len(piece) + 1 > MAX_SENTENCE_CHARS and chunk:
                sentences.append(chunk)
                chunk = piece
            else:
                chunk = f"{chunk}，{piece}" if chunk else piece
        if chunk:
            sentences.append(chunk)
    return sentences


def strip_markdown_for_tts(text: str) -> str:
    """TTS 前清理：去 markdown 语法与代码块（代码块读出来没有意义）。"""
    without_code = re.sub(r"```[\s\S]*?```", "（这里有一段示例代码，详情看屏幕。）", text or "")
    without_code = re.sub(r"`([^`]*)`", r"\1", without_code)
    without_code = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", without_code)
    without_code = re.sub(r"(^|\n)#{1,6}\s*", r"\1", without_code)
    without_code = re.sub(r"(\*\*|__|\*|_)", "", without_code)
    return " ".join(without_code.split())


class TutorVoiceSession:
    """单个 WS 连接的语音会话：管理 ASR / TTS / 轮次任务与打断。"""

    def __init__(
        self,
        *,
        user_id: int,
        send_json: Any,
        tutor_chat: Any,
        mock_vad_seconds: float = 3.0,
    ) -> None:
        self.user_id = user_id
        self.send_json = send_json
        self.tutor_chat = tutor_chat
        self.mock_vad_seconds = mock_vad_seconds
        self.tts: TTSSession | None = None
        self.tts_task: asyncio.Task | None = None
        self.turn_task: asyncio.Task | None = None
        self.asr: ASRProvider | None = None
        self.providers_info = voice_providers_ready()
        self._tts_session_seq = 0
        self._interrupted_turn: str = ""

    # ----------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        await self.send_json({"type": "started", "providers": self.providers_info})

    async def shutdown(self) -> None:
        await self._interrupt_current_turn(notify=False)
        if self.asr:
            try:
                await self.asr.stop()
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------------------- ASR
    async def start_asr(self) -> None:
        async def on_partial(text: str) -> None:
            await self.send_json({"type": "asr_partial", "text": text})

        async def on_final(text: str) -> None:
            await self.send_json({"type": "asr_final", "text": text})
            await self._handle_final_text(text)

        self.asr = build_asr_provider(on_partial=on_partial, on_final=on_final, mock_vad_seconds=self.mock_vad_seconds)
        try:
            await self.asr.start()
            await self.send_json({"type": "asr_ready", "provider": type(self.asr).__name__})
        except Exception as exc:  # noqa: BLE001
            logger.warning("ASR start failed: %s", exc)
            await self.send_json({"type": "error", "message": f"语音识别启动失败：{exc}"})

    async def feed_audio(self, pcm16: bytes) -> None:
        if self.asr:
            self.asr.send_audio_frame(pcm16)

    # -------------------------------------------------------------------- turns
    async def _handle_final_text(self, text: str) -> None:
        if not text.strip():
            return
        await self._interrupt_current_turn(notify=True)
        self.turn_task = asyncio.create_task(self._run_turn(text.strip()))

    async def _run_turn(self, question: str) -> None:
        turn_id = str(uuid.uuid4())
        await self.send_json({"type": "turn_start", "turn_id": turn_id, "question": question})
        try:
            answer = await self.tutor_chat(question)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await self.send_json({"type": "error", "message": f"辅导回答生成失败：{exc}"})
            return

        final_text = (answer or "").strip()
        await self.send_json({"type": "assistant_final", "content": final_text})
        await self._speak_answer(final_text)

    async def _speak_answer(self, answer: str) -> None:
        """句级切分 → 逐句启动 TTS 会话（伯乐同款衔接），音频帧实时下行。"""
        sentences = split_sentences(strip_markdown_for_tts(answer))
        if not sentences:
            return
        try:
            self.tts = build_tts_session()
        except Exception as exc:  # noqa: BLE001
            await self.send_json({"type": "error", "message": f"语音合成不可用：{exc}"})
            return

        self._tts_session_seq += 1
        session_id = f"tts-{self.user_id}-{self._tts_session_seq}"
        tts = self.tts
        try:
            await tts.start(session_id, user_id=str(self.user_id))
            for sentence in sentences:
                await tts.send_text(session_id, sentence, user_id=str(self.user_id))
            await tts.finish(session_id)

            async for frame in tts.audio_frames():
                await self.send_json({"type": "tts_audio", "data": frame.hex()})
            await self.send_json({"type": "turn_end"})
        except asyncio.CancelledError:
            try:
                await tts.cancel(session_id)
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            close = getattr(tts, "close", None)
            if close:
                try:
                    await close()
                except Exception:  # noqa: BLE001
                    pass
            if self.tts is tts:
                self.tts = None

    # ----------------------------------------------------------------- interrupt
    async def interrupt(self) -> None:
        await self._interrupt_current_turn(notify=True)

    async def _interrupt_current_turn(self, *, notify: bool) -> None:
        """伯乐 _interrupt_current_turn：停 TTS + 取消轮次任务 + 通知前端。"""
        if self.turn_task and not self.turn_task.done():
            self.turn_task.cancel()
            try:
                await self.turn_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                pass
            self.turn_task = None
        if notify:
            await self.send_json({"type": "interrupted", "message": "已停止当前播报，继续聆听"})
