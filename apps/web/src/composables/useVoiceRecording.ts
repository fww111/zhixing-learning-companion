/**
 * 麦克风原始音频录音 composable（issue #11 前端部分）。
 *
 * 与现有 Web Speech API 的"浏览器内置听写"不同，这里通过 getUserMedia + MediaRecorder
 * 拿到原始音频 Blob，是将来接后端 ASR（豆包/阿里云，issue #11 方案 b）的前置能力。
 *
 * 隐私：音频仅在本地采集，是否上传完全由调用方通过 onAudioReady 决定；
 * 没有任何默认网络发送。
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceRecordingState = "idle" | "recording" | "stopped" | "error";

export interface VoiceRecordingResult {
  blob: Blob;
  mimeType: string;
  durationMs: number;
  /** 本地预览/回放地址，调用方负责在用完后 revokeObjectURL */
  url: string;
}

export interface VoiceRecordingStatus {
  state: VoiceRecordingState;
  isRecording: boolean;
  durationMs: number;
  error: string | null;
  mimeType: string | null;
}

export interface UseVoiceRecordingOptions {
  /** 录音完成（停止）后触发，调用方可在此把 Blob 上传到后端 ASR；默认不发送任何请求 */
  onAudioReady?: (result: VoiceRecordingResult) => void;
  /** 期望的单次最长时长，到时自动停止，默认 60s */
  maxDurationMs?: number;
}

const IDLE_STATUS: VoiceRecordingStatus = {
  state: "idle",
  isRecording: false,
  durationMs: 0,
  error: null,
  mimeType: null,
};

/** 按浏览器支持情况挑选录音格式，都不支持时返回空串交给 MediaRecorder 用默认值。 */
export function pickSupportedMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4;codecs=mp4a.40.2",
    "audio/mp4",
  ];
  if (typeof MediaRecorder === "undefined") return "";
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

export function describeError(error: unknown): string {
  if (error instanceof DOMException) {
    switch (error.name) {
      case "NotAllowedError":
        return "麦克风权限被拒绝，请在浏览器地址栏允许使用麦克风后重试。";
      case "NotFoundError":
        return "未检测到麦克风设备，请检查耳机或麦克风是否连接。";
      case "NotReadableError":
        return "麦克风被其他应用占用，请关闭占用后重试。";
      default:
        return `录音失败：${error.name}`;
    }
  }
  return error instanceof Error ? error.message : "录音失败，请稍后再试。";
}

export function useVoiceRecording(options?: UseVoiceRecordingOptions) {
  const maxDurationMs = options?.maxDurationMs ?? 60_000;
  const onAudioReadyRef = useRef(options?.onAudioReady);
  onAudioReadyRef.current = options?.onAudioReady;

  const [status, setStatus] = useState<VoiceRecordingStatus>(IDLE_STATUS);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const stopResolverRef = useRef<((result: VoiceRecordingResult) => void) | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const releaseStream = useCallback(() => {
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }
  }, []);

  const start = useCallback(async (): Promise<void> => {
    if (typeof navigator?.mediaDevices?.getUserMedia !== "function" || typeof MediaRecorder === "undefined") {
      const message = "当前浏览器不支持麦克风录音，请使用较新的 Chrome、Edge 或 Safari。";
      setStatus({ ...IDLE_STATUS, state: "error", error: message });
      throw new Error(message);
    }
    if (recorderRef.current?.state === "recording") return;

    setStatus({ ...IDLE_STATUS, state: "recording", isRecording: true });
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;

      const mimeType = pickSupportedMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onstop = () => {
        const actualMimeType = recorder.mimeType || mimeType || "audio/webm";
        const durationMs = Math.max(0, performance.now() - startedAtRef.current);
        const blob = new Blob(chunksRef.current, { type: actualMimeType });
        const url = URL.createObjectURL(blob);
        const result: VoiceRecordingResult = { blob, mimeType: actualMimeType, durationMs, url };

        setStatus({
          state: "stopped",
          isRecording: false,
          durationMs: Math.round(durationMs),
          error: null,
          mimeType: actualMimeType,
        });
        releaseStream();
        try {
          onAudioReadyRef.current?.(result);
        } catch {
          // 回调失败不影响本地录音结果
        }
        stopResolverRef.current?.(result);
        stopResolverRef.current = null;
      };

      startedAtRef.current = performance.now();
      recorder.start();
      timerRef.current = window.setInterval(() => {
        const elapsed = performance.now() - startedAtRef.current;
        setStatus((prev) => ({ ...prev, durationMs: Math.round(elapsed) }));
        if (elapsed >= maxDurationMs) {
          void stop();
        }
      }, 200);
    } catch (error) {
      const message = describeError(error);
      clearTimer();
      releaseStream();
      setStatus({ ...IDLE_STATUS, state: "error", error: message });
      throw error instanceof Error ? error : new Error(message);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clearTimer, releaseStream, maxDurationMs]);

  const stop = useCallback((): Promise<VoiceRecordingResult> => {
    return new Promise((resolve) => {
      const recorder = recorderRef.current;
      clearTimer();
      if (!recorder || recorder.state === "inactive") {
        releaseStream();
        // 兜底：没有进行中的录音时返回一个空结果承诺，避免调用方挂起
        const fallback: VoiceRecordingResult = {
          blob: new Blob([], { type: "audio/webm" }),
          mimeType: "audio/webm",
          durationMs: 0,
          url: "",
        };
        resolve(fallback);
        return;
      }
      stopResolverRef.current = resolve;
      recorder.stop();
    });
  }, [clearTimer, releaseStream]);

  const reset = useCallback(() => {
    clearTimer();
    releaseStream();
    recorderRef.current = null;
    chunksRef.current = [];
    setStatus(IDLE_STATUS);
  }, [clearTimer, releaseStream]);

  // 组件卸载时释放麦克风，避免设备指示灯一直亮着
  useEffect(() => {
    return () => {
      clearTimer();
      if (recorderRef.current?.state === "recording") {
        recorderRef.current.onstop = null;
        try {
          recorderRef.current.stop();
        } catch {
          // 卸载阶段忽略停止异常
        }
      }
      releaseStream();
    };
  }, [clearTimer, releaseStream]);

  return { status, start, stop, reset };
}
