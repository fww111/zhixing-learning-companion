import asyncio
import json
import struct

import pytest

from app.services.doubao_protocol import (
    DOUBAO_SAMPLE_RATE,
    DoubaoEventType,
    DoubaoMsgType,
    DoubaoMsgTypeFlagBits,
    decode_message,
    encode_event_message,
    session_start_payload,
    task_request_payload,
)
from app.services.tutor_voice_service import (
    VOICE_SESSION_TOKEN_TTL_SECONDS,
    create_voice_session_token,
    decode_voice_session_token,
    split_sentences,
    strip_markdown_for_tts,
)
from app.services.voice_providers import MockASRProvider, MockTTSSession, voice_providers_ready


def test_doubao_event_encode_decode_roundtrip():
    payload = task_request_payload("sess-1", "你好")
    frame = encode_event_message(DoubaoEventType.TaskRequest, payload, "sess-1")
    message = decode_message(frame)

    assert message.type == DoubaoMsgType.FullClientRequest
    assert message.flag == DoubaoMsgTypeFlagBits.WithEvent
    assert message.event == DoubaoEventType.TaskRequest
    assert message.session_id == "sess-1"
    assert message.payload == payload


def test_doubao_connection_level_event_has_no_session():
    frame = encode_event_message(DoubaoEventType.StartConnection, b"{}")
    message = decode_message(frame)
    assert message.event == DoubaoEventType.StartConnection
    assert message.session_id == ""
    assert message.connect_id == ""
    assert message.payload == b"{}"


def test_session_start_payload_requests_pcm24k():
    payload = json.loads(session_start_payload("s1").decode("utf-8"))
    assert payload["namespace"] == "BidirectionalTTS"
    assert payload["req_params"]["audio_params"]["format"] == "pcm"
    assert payload["req_params"]["audio_params"]["sample_rate"] == DOUBAO_SAMPLE_RATE


def test_split_sentences_by_terminal_punctuation():
    text = "贪心算法的核心是局部最优。每一步都选当前最好的选项！最后需要注意反例；常见陷阱是排序依据。"
    sentences = split_sentences(text)
    assert len(sentences) == 4
    assert sentences[0].endswith("局部最优。")
    assert sentences[1].endswith("选项！")
    assert sentences[2].endswith("反例；")


def test_split_sentences_splits_long_sentence_by_comma():
    sentence = "这是一个特别长的句子，" + "，".join(["补充要点" for _ in range(30)]) + "。"
    sentences = split_sentences(sentence)
    assert all(len(item) <= 120 for item in sentences)
    assert "".join(sentences).replace("，", "，").startswith("这是一个特别长的句子")


def test_split_sentences_empty():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_strip_markdown_for_tts_removes_code_and_links():
    text = "## 标题\n看这段代码：\n```cpp\nint main() {}\n```\n参考[链接](https://example.com)与 `变量`。"
    cleaned = strip_markdown_for_tts(text)
    assert "int main" not in cleaned
    assert "https://" not in cleaned
    assert "示例代码" in cleaned
    assert "##" not in cleaned
    assert "`" not in cleaned


def test_voice_session_token_roundtrip():
    token = create_voice_session_token(user_id=7, course_id=3, node_id="node-6-3")
    claims = decode_voice_session_token(token)
    assert claims["session_type"] == "tutor_voice"
    assert claims["user_id"] == 7
    assert claims["course_id"] == 3
    assert claims["node_id"] == "node-6-3"
    assert claims["voice_session_id"]


def test_voice_session_token_rejects_wrong_type():
    token = create_voice_session_token(user_id=7, course_id=3)
    # 登录态 JWT（sub 存在但 session_type 不是 tutor_voice）应被拒绝
    login_like = token.replace("tutor_voice", "login") if "tutor_voice" in token else None
    with pytest.raises(Exception):
        decode_voice_session_token("not-a-token")
    if login_like:
        with pytest.raises(Exception):
            decode_voice_session_token(login_like)


def test_mock_tts_session_produces_silence_frames_and_cancel():
    async def scenario():
        session = MockTTSSession()
        await session.start("s", user_id="u")
        await session.send_text("s", "一段用于演示的文本内容", user_id="u")
        await session.finish("s")
        frames = [frame async for frame in session.audio_frames()]
        assert frames, "mock tts should yield frames"
        for frame in frames:
            samples = struct.unpack(f"<{len(frame) // 2}h", frame)
            assert all(sample == 0 for sample in samples), "mock frames are silence"
        return len(frames)

    frame_count = asyncio.run(scenario())
    assert 1 <= frame_count <= 10


def test_mock_asr_provider_emits_final_after_vad():
    async def scenario():
        partials: list[str] = []
        finals: list[str] = []

        async def on_partial(text: str) -> None:
            partials.append(text)

        async def on_final(text: str) -> None:
            finals.append(text)

        provider = MockASRProvider(on_partial=on_partial, on_final=on_final, vad_seconds=0.05)
        await provider.start()
        provider.send_audio_frame(b"\x00\x00" * 160)
        await asyncio.sleep(0.15)
        await provider.stop()
        return partials, finals

    partials, finals = asyncio.run(scenario())
    assert finals and "演示模式" in finals[0]
    assert partials


def test_voice_providers_ready_reports_keys():
    info = voice_providers_ready()
    assert set(info) == {"tts_provider", "asr_provider", "doubao_key_present", "dashscope_key_present"}



# ---------------------------------------------------------------- WS endpoint
def test_ws_voice_requires_valid_tokens(tmp_path):
    from fastapi.testclient import TestClient

    from app.db import Base, create_engine_for_url, create_session_factory
    from app.main import create_app
    from app.services.tutor_voice_service import create_voice_session_token

    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'voice-ws.db'}")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(create_app(session_factory=session_factory))

    from starlette.websockets import WebSocketDisconnect as _WsDisconnect

    with pytest.raises(_WsDisconnect):
        with client.websocket_connect("/ws/tutor-voice"):
            pass

    auth = client.post(
        "/api/auth/register",
        json={"username": "voiceuser", "email": "voice@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]

    # 语音会话 JWT 与登录用户不匹配 → 4403（accept 前拒绝同样表现为握手断开）
    foreign_session = create_voice_session_token(user_id=999, course_id=1)
    with pytest.raises(_WsDisconnect):
        with client.websocket_connect(
            f"/ws/tutor-voice?token={token}&voice_session={foreign_session}"
        ):
            pass

    # 合法双 token → started
    good_session = create_voice_session_token(user_id=1, course_id=1, node_id="n1")
    with client.websocket_connect(
        f"/ws/tutor-voice?token={token}&voice_session={good_session}"
    ) as ws:
        started = ws.receive_json()
        assert started["type"] == "started"
        assert "providers" in started


def test_ws_voice_full_turn_with_mock_providers(tmp_path, monkeypatch):
    """mock ASR + mock TTS 全轮次：音频上行 → ASR final → RAG 回答 → TTS 帧 → turn_end。"""
    import os

    from fastapi.testclient import TestClient

    from app.db import Base, create_engine_for_url, create_session_factory
    from app.main import create_app

    monkeypatch.setenv("VOICE_MOCK_VAD_SECONDS", "0.05")
    monkeypatch.setenv("VOICE_TTS_PROVIDER", "mock")
    monkeypatch.setenv("VOICE_ASR_PROVIDER", "mock")

    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'voice-turn.db'}")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(create_app(session_factory=session_factory))

    auth = client.post(
        "/api/auth/register",
        json={"username": "voiceflow", "email": "vf@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    course = client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "C++ Algorithms"},
    )
    course_id = course.json()["id"]

    from app.services.tutor_voice_service import create_voice_session_token

    voice_session = create_voice_session_token(user_id=1, course_id=course_id, node_id="n1")

    with client.websocket_connect(
        f"/ws/tutor-voice?token={token}&voice_session={voice_session}"
    ) as ws:
        assert ws.receive_json()["type"] == "started"
        ws.send_json({"type": "start_asr"})
        asr_ready = ws.receive_json()
        assert asr_ready["type"] == "asr_ready"

        # 上行 300ms 16k 静音音频帧
        silence = "00" * (16000 // 10 * 2)
        for _ in range(6):
            ws.send_json({"type": "audio", "data": silence})

        # 收集消息直到 turn_end 或 error（mock 链路全自动化）
        types = []
        for _ in range(40):
            message = ws.receive_json()
            types.append(message["type"])
            if message["type"] in {"turn_end", "error"}:
                break
        assert "asr_final" in types, f"should get asr_final, got {types}"
        assert "assistant_final" in types, f"should get assistant_final, got {types}"
        assert "tts_audio" in types, f"mock tts should stream frames, got {types}"
        assert types[-1] == "turn_end", f"turn should finish, got {types}"


def test_voice_session_endpoint_issues_short_lived_token(tmp_path):
    from fastapi.testclient import TestClient

    from app.db import Base, create_engine_for_url, create_session_factory
    from app.main import create_app

    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'voice-session.db'}")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(create_app(session_factory=session_factory))

    auth = client.post(
        "/api/auth/register",
        json={"username": "vsession", "email": "vs@example.com", "password": "secret123"},
    )
    token = auth.json()["access_token"]
    course = client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "C++"},
    )
    course_id = course.json()["id"]

    response = client.post(
        "/api/tutor-voice/session",
        headers={"Authorization": f"Bearer {token}"},
        json={"course_id": course_id, "node_id": "n1"},
    )
    assert response.status_code == 200
    payload = response.json()
    claims = decode_voice_session_token(payload["voice_session"])
    assert claims["user_id"] == 1
    assert claims["course_id"] == course_id
    assert payload["expires_in_seconds"] == 4 * 3600

    # 未登录被拒
    assert client.post("/api/tutor-voice/session", json={"course_id": course_id}).status_code == 401
