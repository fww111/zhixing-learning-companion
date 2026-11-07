/**
 * 真·实时双向语音会话（issue #21）。
 *
 * 链路：getUserMedia → AudioWorklet 采集 PCM16k 上行 →
 * 后端 Fun-ASR（3s 静音 VAD 断句）→ 辅导 RAG → 豆包双向 TTS →
 * PCM24k 音频帧下行 → audioContext.currentTime 排队无缝播放（伯乐同款）。
 *
 * 打断：用户点击打断（或后端 VAD 判定新问题）→ 取消 TTS 播放队列 + 后端取消合成。
 * 降级：WebSocket 断开/不支持 AudioWorklet 时回落到大屏既有浏览器语音方案。
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type RealtimeVoicePhase = "idle" | "connecting" | "listening" | "thinking" | "speaking";

export interface RealtimeVoiceMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export interface RealtimeVoiceStatus {
  phase: RealtimeVoicePhase;
  partialText: string;
  error: string;
  ttsProvider: string;
  asrProvider: string;
}

interface UseRealtimeVoiceOptions {
  token: string | undefined;
  voiceSession: string | undefined;
  /** ASR 最终识别文本（用户说完一句） */
  onUserFinal: (text: string) => void;
  /** AI 完整回答文本（用于写进大屏消息列表） */
  onAssistantFinal: (text: string) => void;
}

const UPSTREAM_FRAME_MS = 100;
const UPSTREAM_SAMPLE_RATE = 16_000;
const TTS_SAMPLE_RATE = 24_000;

const WORKLET_SOURCE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Int16Array(1280); // 80ms @16k
    this._offset = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channel = input[0];
    for (let i = 0; i < channel.length; i++) {
      const sample = Math.max(-1, Math.min(1, channel[i]));
      this._buffer[this._offset++] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      if (this._offset >= this._buffer.length) {
        this.port.postMessage(this._buffer.slice(0));
        this._offset = 0;
      }
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCaptureProcessor);
`;

function hexToFloat32(hex: string): Float32Array<ArrayBuffer> {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  const view = new DataView(bytes.buffer);
  const samples = new Float32Array(new ArrayBuffer(bytes.length / 2 * 4));
  for (let i = 0; i < samples.length; i++) {
    samples[i] = view.getInt16(i * 2, true) / 0x8000;
  }
  return samples;
}

export function useRealtimeVoice({ token, voiceSession, onUserFinal, onAssistantFinal }: UseRealtimeVoiceOptions) {
  const [status, setStatus] = useState<RealtimeVoiceStatus>({
    phase: "idle",
    partialText: "",
    error: "",
    ttsProvider: "",
    asrProvider: ""
  });

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const playbackSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const playbackClockRef = useRef(0);
  const phaseRef = useRef<RealtimeVoicePhase>("idle");
  const currentTranscriptRef = useRef("");
  const voiceSessionRef = useRef(voiceSession);
  voiceSessionRef.current = voiceSession;

  const setPhase = useCallback((phase: RealtimeVoicePhase) => {
    phaseRef.current = phase;
    setStatus((current) => ({ ...current, phase }));
  }, []);

  /** 清空 TTS 播放队列并停掉所有已排队的音源（打断的核心动作）。 */
  const flushPlaybackQueue = useCallback(() => {
    for (const source of playbackSourcesRef.current) {
      try {
        source.stop();
      } catch {
        // 已播放完的节点 stop 会抛错，忽略
      }
    }
    playbackSourcesRef.current = [];
    playbackClockRef.current = 0;
  }, []);

  const handleServerMessage = useCallback(
    (event: MessageEvent) => {
      let message: Record<string, unknown>;
      try {
        message = JSON.parse(String(event.data));
      } catch {
        return;
      }
      const type = String(message.type || "");
      switch (type) {
        case "started": {
          const providers = (message.providers || {}) as Record<string, string>;
          setStatus((current) => ({
            ...current,
            ttsProvider: providers.tts_provider || "",
            asrProvider: providers.asr_provider || ""
          }));
          wsRef.current?.send(JSON.stringify({ type: "start_asr" }));
          break;
        }
        case "asr_ready":
          setPhase("listening");
          break;
        case "asr_partial":
          setStatus((current) => ({ ...current, partialText: String(message.text || "") }));
          break;
        case "asr_final": {
          const text = String(message.text || "").trim();
          setStatus((current) => ({ ...current, partialText: "" }));
          if (text) {
            currentTranscriptRef.current = text;
            onUserFinal(text);
          }
          break;
        }
        case "turn_start":
          setPhase("thinking");
          // 用户开口说下一句时后端会打断；前端同步清队列
          flushPlaybackQueue();
          break;
        case "assistant_final":
          onAssistantFinal(String(message.content || ""));
          break;
        case "tts_audio": {
          setPhase("speaking");
          const ctx = playbackCtxRef.current;
          if (!ctx) break;
          const samples = hexToFloat32(String(message.data || ""));
          if (!samples.length) break;
          const buffer = ctx.createBuffer(1, samples.length, TTS_SAMPLE_RATE);
          buffer.copyToChannel(samples, 0);
          const source = ctx.createBufferSource();
          source.buffer = buffer;
          source.connect(ctx.destination);
          // 无缝排队：从上一个帧结束点继续（落后于当前时间则立刻播）
          const startAt = Math.max(playbackClockRef.current, ctx.currentTime + 0.05);
          source.start(startAt);
          playbackClockRef.current = startAt + buffer.duration;
          playbackSourcesRef.current.push(source);
          source.onended = () => {
            playbackSourcesRef.current = playbackSourcesRef.current.filter((item) => item !== source);
            if (!playbackSourcesRef.current.length && phaseRef.current === "speaking") {
              setPhase("listening");
            }
          };
          break;
        }
        case "interrupted":
          flushPlaybackQueue();
          setPhase("listening");
          break;
        case "turn_end":
          flushPlaybackQueue();
          setPhase("listening");
          break;
        case "error":
          setStatus((current) => ({ ...current, error: String(message.message || "语音链路错误") }));
          break;
      }
    },
    [flushPlaybackQueue, onAssistantFinal, onUserFinal, setPhase]
  );

  const start = useCallback(async () => {
    if (!token || !voiceSessionRef.current || wsRef.current) {
      return;
    }
    setPhase("connecting");
    setStatus((current) => ({ ...current, error: "", partialText: "" }));
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      streamRef.current = stream;

      // 采集上下文：浏览器自动把麦克风重采样到 16k
      const captureCtx = new AudioContext({ sampleRate: UPSTREAM_SAMPLE_RATE });
      audioContextRef.current = captureCtx;
      const blobUrl = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "application/javascript" }));
      await captureCtx.audioWorklet.addModule(blobUrl);
      URL.revokeObjectURL(blobUrl);

      const playbackCtx = new AudioContext({ sampleRate: TTS_SAMPLE_RATE });
      playbackCtxRef.current = playbackCtx;
      playbackClockRef.current = 0;

      const ws = new WebSocket(`/ws/tutor-voice?token=${encodeURIComponent(token)}&voice_session=${encodeURIComponent(voiceSessionRef.current || "")}`);
      wsRef.current = ws;
      ws.onmessage = handleServerMessage;
      ws.onerror = () => setStatus((current) => ({ ...current, error: "语音通道连接失败，可改用键盘/听写模式" }));
      ws.onclose = () => {
        wsRef.current = null;
        setPhase("idle");
      };

      await new Promise<void>((resolve, reject) => {
        ws.addEventListener("open", () => resolve(), { once: true });
        ws.addEventListener("error", () => reject(new Error("WS 连接失败")), { once: true });
      });

      const worklet = new AudioWorkletNode(captureCtx, "pcm-capture");
      workletNodeRef.current = worklet;
      worklet.port.onmessage = (event: MessageEvent<Int16Array>) => {
        if (wsRef.current?.readyState !== WebSocket.OPEN) {
          return;
        }
        // 转发到主线程再转 hex，避免在 worklet 里做序列化
        const pcm = event.data as Int16Array;
        let hex = "";
        const view = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
        for (const byte of view) {
          hex += byte.toString(16).padStart(2, "0");
        }
        wsRef.current?.send(JSON.stringify({ type: "audio", data: hex }));
      };
      const source = captureCtx.createMediaStreamSource(stream);
      source.connect(worklet);
      // 不连 destination：避免回声（麦放回路）
    } catch (caught) {
      setStatus((current) => ({
        ...current,
        error: caught instanceof Error ? caught.message : "实时语音启动失败"
      }));
      setPhase("idle");
      stop();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handleServerMessage, onAssistantFinal, onUserFinal, setPhase, token, voiceSession]);

  const stop = useCallback(() => {
    try {
      wsRef.current?.send(JSON.stringify({ type: "stop" }));
    } catch {
      // 连接可能已断
    }
    wsRef.current?.close();
    wsRef.current = null;
    flushPlaybackQueue();
    workletNodeRef.current?.disconnect();
    workletNodeRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
    playbackCtxRef.current?.close().catch(() => undefined);
    playbackCtxRef.current = null;
    setPhase("idle");
    setStatus((current) => ({ ...current, partialText: "" }));
  }, [flushPlaybackQueue, setPhase]);

  /** 用户主动打断 AI 播报（点击大屏打断按钮）。 */
  const interrupt = useCallback(() => {
    flushPlaybackQueue();
    try {
      wsRef.current?.send(JSON.stringify({ type: "interrupt" }));
    } catch {
      // 忽略
    }
    setPhase("listening");
  }, [flushPlaybackQueue, setPhase]);

  /** 摄像头专注状态变化同步给后端（复用 #15 通道）。 */
  const sendAttentionState = useCallback((state: string) => {
    try {
      wsRef.current?.send(JSON.stringify({ type: "attention_state", state }));
    } catch {
      // 忽略
    }
  }, []);

  useEffect(() => stop, [stop]);

  return { status, start, stop, interrupt, sendAttentionState };
}
