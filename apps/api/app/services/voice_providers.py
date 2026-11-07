"""语音 Provider 抽象层（issue #21）。

TTS/ASR 均为可插拔 Provider，由环境变量切换：
- VOICE_TTS_PROVIDER: mock | doubao | edge（edge 走既有 /api/tts/speak，不在此处）
- VOICE_ASR_PROVIDER: mock | funasr | browser（browser 为前端 SpeechRecognition 降级）

无 Key / 未安装 SDK 时工厂自动降级到 MockVoiceProvider，保证链路可演示：
ASR 识别固定提示句，TTS 产出短促静音 PCM，前端状态机照常流转。
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import struct
import time
from typing import AsyncIterator, Awaitable, Callable

import websockets

from app.services.doubao_protocol import (
    DOUBAO_CHAR_DELAY_SECONDS,
    DOUBAO_DEFAULT_RESOURCE_ID,
    DOUBAO_DEFAULT_SPEAKER,
    DOUBAO_SAMPLE_RATE,
    DOUBAO_TTS_WS_URL,
    DoubaoEventType,
    DoubaoMsgType,
    decode_message,
    encode_event_message,
    session_start_payload,
    task_request_payload,
)

logger = logging.getLogger(__name__)

ASR_SAMPLE_RATE = 16_000
ASR_SENTENCE_SILENCE_MS = 3_000
ASR_MODEL = "fun-asr-realtime"

# Mock TTS：300ms 24k 16bit 静音，演示状态机用
MOCK_TTS_SILENCE_MS = 300


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


class VoiceProviderUnavailable(RuntimeError):
    """缺少 Key 或 SDK 时抛出，由工厂降级到 mock。"""


class TTSSession:
    """一次 TTS 会话：送文本 → 流式收 PCM 帧。"""

    async def start(self, session_id: str, *, user_id: str) -> None:
        raise NotImplementedError

    async def send_text(self, session_id: str, text: str, *, user_id: str) -> None:
        raise NotImplementedError

    async def finish(self, session_id: str) -> None:
        raise NotImplementedError

    async def cancel(self, session_id: str) -> None:
        raise NotImplementedError

    async def audio_frames(self) -> AsyncIterator[bytes]:
        raise NotImplementedError
        yield b""  # pragma: no cover

    async def close(self) -> None:
        raise NotImplementedError


class ASRProvider:
    """实时 ASR：send_audio_frame(PCM16) → on_partial/on_final 回调。"""

    async def start(self) -> None:
        raise NotImplementedError

    def send_audio_frame(self, pcm16: bytes) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError


class MockTTSSession(TTSSession):
    """无 Key 演示：产出静音 PCM 帧并回显事件，让前端状态机可跑通。"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._cancelled = False

    async def start(self, session_id: str, *, user_id: str) -> None:
        return

    async def send_text(self, session_id: str, text: str, *, user_id: str) -> None:
        # 按 300ms 一帧静音，帧数与文本长度成正比，演示"边合成边收帧"
        frames = max(1, min(10, math.ceil(len(text) / 20)))
        for _ in range(frames):
            if self._cancelled:
                return
            samples = int(DOUBAO_SAMPLE_RATE * MOCK_TTS_SILENCE_MS / 1000)
            await self._queue.put(struct.pack(f"<{samples}h", *([0] * samples)))

    async def finish(self, session_id: str) -> None:
        if not self._cancelled:
            await self._queue.put(None)

    async def cancel(self, session_id: str) -> None:
        self._cancelled = True
        await self._queue.put(None)

    async def audio_frames(self) -> AsyncIterator[bytes]:
        while True:
            frame = await self._queue.get()
            if frame is None:
                return
            yield frame

    async def close(self) -> None:
        self._cancelled = True


class MockASRProvider(ASRProvider):
    """无 Key 演示：模拟 3 秒静音 VAD 后返回固定提示句（延迟可配置便于测试）。"""

    def __init__(
        self,
        *,
        on_partial: Callable[[str], Awaitable[None]],
        on_final: Callable[[str], Awaitable[None]],
        vad_seconds: float = 3.0,
    ) -> None:
        self.on_partial = on_partial
        self.on_final = on_final
        self.vad_seconds = vad_seconds
        self._received = 0
        self._timer: asyncio.Task | None = None

    async def start(self) -> None:
        self._timer = asyncio.create_task(self._emit_after_vad())

    async def _emit_after_vad(self) -> None:
        await asyncio.sleep(self.vad_seconds)
        await self.on_partial("（演示模式）这个问题我想请老师讲一讲")
        await self.on_final("（演示模式）这个问题我想请老师讲一讲")

    def send_audio_frame(self, pcm16: bytes) -> None:
        self._received += len(pcm16)

    async def stop(self) -> None:
        if self._timer and not self._timer.done():
            self._timer.cancel()


class DoubaoBidirectionalTTSSession(TTSSession):
    """豆包双向流式 TTS 会话（伯乐同款衔接：逐字送文、边合成边收帧）。"""

    def __init__(self, app_id: str, access_key: str) -> None:
        self.app_id = app_id
        self.access_key = access_key
        self._ws = None
        self._connect_id = ""
        self._listen_task: asyncio.Task | None = None
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            DOUBAO_TTS_WS_URL,
            additional_headers={
                "X-Api-App-Key": self.app_id,
                "X-Api-Access-Key": self.access_key,
                "X-Api-Resource-Id": DOUBAO_DEFAULT_RESOURCE_ID,
                "X-Api-Connect-Id": self._connect_id,
            },
            max_size=10 * 1024 * 1024,
        )
        await self._ws.send(encode_event_message(DoubaoEventType.StartConnection, b"{}"))
        response = decode_message(await self._ws.recv())
        if response.event != DoubaoEventType.ConnectionStarted:
            raise VoiceProviderUnavailable(f"豆包 TTS 建连失败 event={response.event}")
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self) -> None:
        try:
            while True:
                message = decode_message(await self._ws.recv())
                if message.type == DoubaoMsgType.AudioOnlyServer and message.payload:
                    await self._queue.put(message.payload)
                elif message.type == DoubaoMsgType.Error:
                    logger.warning("doubao tts error code=%s", message.error_code)
                    await self._queue.put(None)
                    return
                elif message.event in {DoubaoEventType.SessionFinished, DoubaoEventType.SessionCanceled, DoubaoEventType.SessionFailed}:
                    await self._queue.put(None)
                    return
        except Exception as exc:  # noqa: BLE001
            logger.warning("doubao tts listen loop ended: %s", exc)
            await self._queue.put(None)

    async def start(self, session_id: str, *, user_id: str) -> None:
        await self.connect()
        await self._ws.send(encode_event_message(DoubaoEventType.StartSession, session_start_payload(session_id, uid=user_id), session_id))

    async def send_text(self, session_id: str, text: str, *, user_id: str) -> None:
        # 伯乐模式：逐字符送文模拟流式 LLM 输入，豆包按句返回音频
        for char in text:
            await self._ws.send(encode_event_message(DoubaoEventType.TaskRequest, task_request_payload(session_id, char, uid=user_id), session_id))
            await asyncio.sleep(DOUBAO_CHAR_DELAY_SECONDS)

    async def finish(self, session_id: str) -> None:
        await self._ws.send(encode_event_message(DoubaoEventType.FinishSession, b"{}", session_id))

    async def cancel(self, session_id: str) -> None:
        try:
            await self._ws.send(encode_event_message(DoubaoEventType.CancelSession, b"{}", session_id))
        except Exception:  # noqa: BLE001
            pass
        await self._queue.put(None)

    async def audio_frames(self) -> AsyncIterator[bytes]:
        while True:
            frame = await self._queue.get()
            if frame is None:
                return
            yield frame

    async def close(self) -> None:
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        if self._ws is not None:
            try:
                await self._ws.send(encode_event_message(DoubaoEventType.FinishConnection, b"{}"))
            except Exception:  # noqa: BLE001
                pass
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None


class FunASRProvider(ASRProvider):
    """阿里云 DashScope Fun-ASR 实时识别（3s 静音 VAD 断句）。

    dashscope Recognition 为同步 SDK，伯乐模式：工作线程回调 →
    asyncio.run_coroutine_threadsafe 桥接回事件循环。
    """

    def __init__(
        self,
        api_key: str,
        *,
        on_partial: Callable[[str], Awaitable[None]],
        on_final: Callable[[str], Awaitable[None]],
    ) -> None:
        self.api_key = api_key
        self.on_partial = on_partial
        self.on_final = on_final
        self.loop = asyncio.get_running_loop()
        self._recognition = None
        self._stopped = False

    async def start(self) -> None:
        try:
            import dashscope
            from dashscope.audio.asr import Recognition, RecognitionCallback
        except ImportError as exc:  # pragma: no cover
            raise VoiceProviderUnavailable("dashscope SDK 未安装") from exc

        dashscope.api_key = self.api_key

        owner = self

        class _Callback(RecognitionCallback):
            def on_open(self) -> None:
                logger.info("fun-asr connected")

            def on_event(self, result) -> None:
                sentence = result.get_sentence() or {}
                text = str(sentence.get("text") or "").strip()
                if not text:
                    return
                is_final = RecognitionResult.is_sentence_end(sentence) if "RecognitionResult" in globals() else sentence.get("end_time") is not None
                asyncio.run_coroutine_threadsafe(
                    owner.on_final(text) if is_final else owner.on_partial(text),
                    owner.loop,
                )

            def on_error(self, result) -> None:
                logger.warning("fun-asr error: %s", getattr(result, "message", ""))

            def on_close(self) -> None:
                logger.info("fun-asr closed")

        self._recognition = Recognition(
            model=ASR_MODEL,
            format="pcm",
            sample_rate=ASR_SAMPLE_RATE,
            semantic_punctuation_enabled=False,
            multi_threshold_mode_enabled=True,
            max_sentence_silence=ASR_SENTENCE_SILENCE_MS,
            callback=_Callback(),
        )
        await asyncio.to_thread(self._recognition.start)

    def send_audio_frame(self, pcm16: bytes) -> None:
        if self._recognition is None or self._stopped:
            return
        try:
            self._recognition.send_audio_frame(pcm16)
        except Exception as exc:  # noqa: BLE001
            logger.warning("fun-asr send failed: %s", exc)

    async def stop(self) -> None:
        if self._recognition is None or self._stopped:
            return
        self._stopped = True
        await asyncio.to_thread(self._recognition.stop)


def build_tts_session() -> TTSSession:
    """工厂：按环境变量创建 TTS 会话，缺 Key/SDK 自动降级 mock。"""
    provider = _env("VOICE_TTS_PROVIDER").lower()
    app_id = _env("DOUBAO_VOICE_APP_ID")
    access_key = _env("DOUBAO_VOICE_API_KEY")
    if provider == "doubao" or (provider != "mock" and app_id and access_key):
        if not app_id or not access_key:
            raise VoiceProviderUnavailable("缺少 DOUBAO_VOICE_APP_ID / DOUBAO_VOICE_API_KEY")
        return DoubaoBidirectionalTTSSession(app_id, access_key)
    return MockTTSSession()


def build_asr_provider(
    *,
    on_partial: Callable[[str], Awaitable[None]],
    on_final: Callable[[str], Awaitable[None]],
    mock_vad_seconds: float = 3.0,
) -> ASRProvider:
    """工厂：按环境变量创建 ASR Provider，缺 Key/SDK 自动降级 mock。"""
    provider = _env("VOICE_ASR_PROVIDER").lower()
    api_key = _env("DASHSCOPE_API_KEY")
    if provider == "funasr" or (provider != "mock" and api_key):
        if not api_key:
            raise VoiceProviderUnavailable("缺少 DASHSCOPE_API_KEY")
        return FunASRProvider(api_key, on_partial=on_partial, on_final=on_final)
    return MockASRProvider(on_partial=on_partial, on_final=on_final, vad_seconds=mock_vad_seconds)


def voice_providers_ready() -> dict[str, str]:
    """观测接口：当前语音引擎配置状态（供 WS start 响应与诊断）。"""
    tts_provider = "doubao" if (_env("DOUBAO_VOICE_APP_ID") and _env("DOUBAO_VOICE_API_KEY")) else ("mock" if _env("VOICE_TTS_PROVIDER") == "mock" else "mock")
    asr_provider = "funasr" if _env("DASHSCOPE_API_KEY") else "mock"
    return {
        "tts_provider": _env("VOICE_TTS_PROVIDER") or tts_provider,
        "asr_provider": _env("VOICE_ASR_PROVIDER") or asr_provider,
        "doubao_key_present": str(bool(_env("DOUBAO_VOICE_APP_ID") and _env("DOUBAO_VOICE_API_KEY"))).lower(),
        "dashscope_key_present": str(bool(_env("DASHSCOPE_API_KEY"))).lower(),
    }
