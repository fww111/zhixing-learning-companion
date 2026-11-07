"""豆包（火山引擎）双向流式 TTS v3 二进制协议。

移植自自有项目"伯乐 AI-Interview"的 voice_interview_service.py 协议封装
（issue #21 参考：DoubaoBidirectionalTTSClient 同款衔接），裁剪为本项目
所需的最小协议面：建连/会话/逐字送文/收音频帧/取消/断连。

协议要点（v3 unidirectional/bidirectional 通用）：
- 4 字节头：version|header_size、type|flags、serialization|compression、保留
- WithEvent 时附 4 字节 event；会话事件附 session_id 字符串；尾部 4 字节 payload 长度
- 音频帧类型 AudioOnlyServer(0b1011)，事件 TTSSentenceStart/End/Response
"""

from __future__ import annotations

import io
import json
import struct
from dataclasses import dataclass, field
from enum import IntEnum

DOUBAO_TTS_WS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
DOUBAO_DEFAULT_SPEAKER = "zh_male_m191_uranus_bigtts"
DOUBAO_DEFAULT_RESOURCE_ID = "seed-tts-2.0"
DOUBAO_SAMPLE_RATE = 24000
DOUBAO_CHAR_DELAY_SECONDS = 0.005


class DoubaoMsgType(IntEnum):
    Invalid = 0
    FullClientRequest = 0b1
    AudioOnlyClient = 0b10
    FullServerResponse = 0b1001
    AudioOnlyServer = 0b1011
    FrontEndResultServer = 0b1100
    Error = 0b1111


class DoubaoMsgTypeFlagBits(IntEnum):
    NoSeq = 0
    PositiveSeq = 0b1
    LastNoSeq = 0b10
    NegativeSeq = 0b11
    WithEvent = 0b100


class DoubaoVersionBits(IntEnum):
    Version1 = 1


class DoubaoHeaderSizeBits(IntEnum):
    HeaderSize4 = 1


class DoubaoSerializationBits(IntEnum):
    Raw = 0
    JSON = 0b1


class DoubaoCompressionBits(IntEnum):
    None_ = 0


class DoubaoEventType(IntEnum):
    StartConnection = 1
    FinishConnection = 2
    ConnectionStarted = 50
    ConnectionFailed = 51
    ConnectionFinished = 52
    StartSession = 100
    CancelSession = 101
    FinishSession = 102
    SessionStarted = 150
    SessionCanceled = 151
    SessionFinished = 152
    SessionFailed = 153
    TaskRequest = 200
    TTSSentenceStart = 350
    TTSSentenceEnd = 351
    TTSResponse = 352


# 连接级事件（client 请求与 server 响应）：均不携带 session_id 字段
CONNECTION_CONTROL_EVENTS = {
    DoubaoEventType.StartConnection,
    DoubaoEventType.FinishConnection,
}
# server→client 连接响应：携带 connect_id 字段
CONNECTION_RESULT_EVENTS = {
    DoubaoEventType.ConnectionStarted,
    DoubaoEventType.ConnectionFailed,
    DoubaoEventType.ConnectionFinished,
}


@dataclass
class DoubaoMessage:
    version: int = DoubaoVersionBits.Version1
    header_size: int = DoubaoHeaderSizeBits.HeaderSize4
    type: int = DoubaoMsgType.Invalid
    flag: int = DoubaoMsgTypeFlagBits.NoSeq
    serialization: int = DoubaoSerializationBits.JSON
    compression: int = DoubaoCompressionBits.None_
    event: int = 0
    session_id: str = ""
    connect_id: str = ""
    sequence: int = 0
    error_code: int = 0
    payload: bytes = field(default=b"")

    @classmethod
    def from_bytes(cls, data: bytes) -> "DoubaoMessage":
        type_and_flag = data[1]
        msg = cls(
            type=type_and_flag >> 4,
            flag=type_and_flag & 0b00001111,
        )
        msg.unmarshal(data)
        return msg

    def unmarshal(self, data: bytes) -> None:
        buffer = io.BytesIO(data)
        version_and_header_size = buffer.read(1)[0]
        self.version = version_and_header_size >> 4
        self.header_size = version_and_header_size & 0b00001111
        buffer.read(1)  # type|flag 已在 from_bytes 解析
        serialization_compression = buffer.read(1)[0]
        self.serialization = serialization_compression >> 4
        self.compression = serialization_compression & 0b00001111
        header_size = 4 * self.header_size
        if padding := header_size - 3:
            buffer.read(padding)

        if self.type in {
            DoubaoMsgType.FullClientRequest,
            DoubaoMsgType.FullServerResponse,
            DoubaoMsgType.FrontEndResultServer,
            DoubaoMsgType.AudioOnlyClient,
            DoubaoMsgType.AudioOnlyServer,
        } and self.flag in {DoubaoMsgTypeFlagBits.PositiveSeq, DoubaoMsgTypeFlagBits.NegativeSeq}:
            sequence_bytes = buffer.read(4)
            if sequence_bytes:
                self.sequence = struct.unpack(">i", sequence_bytes)[0]
        elif self.type == DoubaoMsgType.Error:
            error_code_bytes = buffer.read(4)
            if error_code_bytes:
                self.error_code = struct.unpack(">I", error_code_bytes)[0]

        if self.flag == DoubaoMsgTypeFlagBits.WithEvent:
            event_bytes = buffer.read(4)
            if event_bytes:
                self.event = struct.unpack(">i", event_bytes)[0]
            if self.event in CONNECTION_RESULT_EVENTS:
                size_bytes = buffer.read(4)
                if size_bytes:
                    size = struct.unpack(">I", size_bytes)[0]
                    if size > 0:
                        self.connect_id = buffer.read(size).decode("utf-8")
            elif self.event not in CONNECTION_CONTROL_EVENTS:
                size_bytes = buffer.read(4)
                if size_bytes:
                    size = struct.unpack(">I", size_bytes)[0]
                    if size > 0:
                        self.session_id = buffer.read(size).decode("utf-8")

        size_bytes = buffer.read(4)
        if size_bytes:
            size = struct.unpack(">I", size_bytes)[0]
            if size > 0:
                self.payload = buffer.read(size)


def encode_event_message(
    event: DoubaoEventType,
    payload: bytes = b"",
    session_id: str = "",
    *,
    serialization: int = DoubaoSerializationBits.JSON,
) -> bytes:
    """编码一条 FullClientRequest + WithEvent 事件帧。"""
    buffer = io.BytesIO()
    header = [
        (DoubaoVersionBits.Version1 << 4) | DoubaoHeaderSizeBits.HeaderSize4,
        (DoubaoMsgType.FullClientRequest << 4) | DoubaoMsgTypeFlagBits.WithEvent,
        (serialization << 4) | DoubaoCompressionBits.None_,
        0x00,
    ]
    buffer.write(bytes(header))
    buffer.write(struct.pack(">i", int(event)))
    if event not in {DoubaoEventType.StartConnection, DoubaoEventType.FinishConnection}:
        session_id_bytes = session_id.encode("utf-8")
        buffer.write(struct.pack(">I", len(session_id_bytes)))
        if session_id_bytes:
            buffer.write(session_id_bytes)
    buffer.write(struct.pack(">I", len(payload)))
    if payload:
        buffer.write(payload)
    return buffer.getvalue()


def decode_message(data: bytes) -> DoubaoMessage:
    return DoubaoMessage.from_bytes(data)


def session_start_payload(session_id: str, *, speaker: str = DOUBAO_DEFAULT_SPEAKER, uid: str = "student") -> bytes:
    """BidirectionalTTS StartSession 载荷：PCM 24k 输出。"""
    return json.dumps(
        {
            "user": {"uid": uid},
            "namespace": "BidirectionalTTS",
            "event": int(DoubaoEventType.StartSession),
            "req_params": {
                "speaker": speaker,
                "audio_params": {"format": "pcm", "sample_rate": DOUBAO_SAMPLE_RATE, "enable_timestamp": True},
                "additions": json.dumps({"disable_markdown_filter": False}, ensure_ascii=False),
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")


def task_request_payload(session_id: str, text: str, *, speaker: str = DOUBAO_DEFAULT_SPEAKER, uid: str = "student") -> bytes:
    """TaskRequest 载荷：送一段待合成文本。"""
    return json.dumps(
        {
            "user": {"uid": uid},
            "namespace": "BidirectionalTTS",
            "event": int(DoubaoEventType.TaskRequest),
            "req_params": {
                "speaker": speaker,
                "audio_params": {"format": "pcm", "sample_rate": DOUBAO_SAMPLE_RATE, "enable_timestamp": True},
                "additions": json.dumps({"disable_markdown_filter": False}, ensure_ascii=False),
                "text": text,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
