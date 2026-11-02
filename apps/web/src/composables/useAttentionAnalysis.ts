/**
 * 学习专注度感知 composable：MediaPipe FaceLandmarker（纯浏览器推理）+ attentionInference 状态机。
 *
 * 隐私约束（issue #14 硬要求）：摄像头画面只在本地解码分析，任何帧/图像都不离开浏览器；
 * 唯一的网络上报是 onSample 回调产出的 JSON 聚合指标（由调用方决定是否发送）。
 */

import { useCallback, useRef, useState } from "react";
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
import {
  AttentionStateMachine,
  AttentionWindowAggregator,
  extractFaceSignals,
  type AttentionStateKey,
  type FaceFrameSignals
} from "./attentionInference";

const WASM_BASE = "/mediapipe/wasm";
const MODEL_URL = "/mediapipe/models/face_landmarker.task";

export interface AttentionSample {
  window_seconds: number;
  distribution: Record<AttentionStateKey, number>;
  dominant: AttentionStateKey;
  captured_at: string;
}

export interface AttentionStatus {
  running: boolean;
  modelReady: boolean;
  error: string | null;
  state: AttentionStateKey;
  confidence: number;
  blinkRatePerMinute: number;
}

const IDLE_STATUS: AttentionStatus = {
  running: false,
  modelReady: false,
  error: null,
  state: "focused",
  confidence: 0,
  blinkRatePerMinute: 0
};

export interface UseAttentionAnalysisOptions {
  /** 聚合指标上报间隔，默认 10s */
  sampleIntervalMs?: number;
  /** 聚合窗口，默认 60s */
  windowMs?: number;
  /** 每达到采样间隔触发一次（由调用方上报画像事件） */
  onSample?: (sample: AttentionSample) => void;
}

export function useAttentionAnalysis(options?: UseAttentionAnalysisOptions) {
  const sampleIntervalMs = options?.sampleIntervalMs ?? 10_000;
  const windowMs = options?.windowMs ?? 60_000;
  const onSampleRef = useRef(options?.onSample);
  onSampleRef.current = options?.onSample;

  const [status, setStatus] = useState<AttentionStatus>(IDLE_STATUS);

  const streamRef = useRef<MediaStream | null>(null);
  const landmarkerRef = useRef<FaceLandmarker | null>(null);
  const rafRef = useRef<number | null>(null);
  const machineRef = useRef(new AttentionStateMachine());
  const aggregatorRef = useRef(new AttentionWindowAggregator());
  const lastSampleAtRef = useRef(0);
  const lastVideoTimeRef = useRef(-1);
  const runningRef = useRef(false);

  const patchStatus = useCallback((patch: Partial<AttentionStatus>) => {
    setStatus((prev) => ({ ...prev, ...patch }));
  }, []);

  const ensureLandmarker = useCallback(async (): Promise<FaceLandmarker> => {
    if (landmarkerRef.current) return landmarkerRef.current;
    const fileset = await FilesetResolver.forVisionTasks(WASM_BASE);
    let landmarker: FaceLandmarker;
    try {
      landmarker = await FaceLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: MODEL_URL, delegate: "GPU" },
        runningMode: "VIDEO",
        numFaces: 1,
        outputFaceBlendshapes: true,
        outputFacialTransformationMatrixes: true
      });
    } catch {
      // 集成显卡/驱动不支持 WebGL 时回退 CPU
      landmarker = await FaceLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: MODEL_URL, delegate: "CPU" },
        runningMode: "VIDEO",
        numFaces: 1,
        outputFaceBlendshapes: true,
        outputFacialTransformationMatrixes: true
      });
    }
    landmarkerRef.current = landmarker;
    patchStatus({ modelReady: true });
    return landmarker;
  }, [patchStatus]);

  const stop = useCallback(() => {
    runningRef.current = false;
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }
    if (landmarkerRef.current) {
      landmarkerRef.current.close();
      landmarkerRef.current = null;
    }
    aggregatorRef.current.reset();
    lastVideoTimeRef.current = -1;
    setStatus((prev) => ({ ...IDLE_STATUS, error: prev.error }));
  }, []);

  const loop = useCallback(
    (video: HTMLVideoElement, landmarker: FaceLandmarker) => {
      if (!runningRef.current) return;

      const detect = (): void => {
        if (!runningRef.current) return;
        if (video.readyState >= 2 && video.currentTime !== lastVideoTimeRef.current) {
          lastVideoTimeRef.current = video.currentTime;
          const nowMs = performance.now();
          let result;
          try {
            result = landmarker.detectForVideo(video, nowMs);
          } catch {
            rafRef.current = requestAnimationFrame(detect);
            return;
          }

          const faceBlendshapes = result.faceBlendshapes?.[0]?.categories ?? [];
          const matrix = result.facialTransformationMatrixes?.[0]?.data;
          const signals: FaceFrameSignals = extractFaceSignals(faceBlendshapes, matrix, nowMs);
          // 临时调试：暴露原始信号供阈值校准（验证完移除）
          (window as unknown as { __attentionDebug?: FaceFrameSignals }).__attentionDebug = signals;
          const snapshot = machineRef.current.update(signals);
          aggregatorRef.current.push(snapshot.state, nowMs);

          const patch: Partial<AttentionStatus> = {
            state: snapshot.state,
            confidence: snapshot.confidence,
            blinkRatePerMinute: Math.round(machineRef.current.blinkRatePerMinute(nowMs))
          };

          if (nowMs - lastSampleAtRef.current >= sampleIntervalMs) {
            lastSampleAtRef.current = nowMs;
            const sample: AttentionSample = {
              window_seconds: Math.round(windowMs / 1000),
              distribution: aggregatorRef.current.distribution(windowMs, nowMs),
              dominant: aggregatorRef.current.dominant(windowMs, nowMs),
              captured_at: new Date().toISOString()
            };
            try {
              onSampleRef.current?.(sample);
            } catch {
              // 上报失败静默：感知功能不得影响学习主流程
            }
          }
          patchStatus(patch);
        }
        rafRef.current = requestAnimationFrame(detect);
      };

      rafRef.current = requestAnimationFrame(detect);
    },
    [patchStatus, sampleIntervalMs, windowMs]
  );

  /** 启动感知：请求摄像头 → 加载模型 → 进入分析循环。失败会抛出（页面侧展示错误并静默降级）。 */
  const start = useCallback(
    async (video: HTMLVideoElement): Promise<void> => {
      if (runningRef.current) return;
      setStatus((prev) => ({ ...prev, running: true, error: null }));
      runningRef.current = true;
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 640, height: 480, facingMode: "user" },
          audio: false
        });
        streamRef.current = stream;
        video.srcObject = stream;
        // 授权弹窗等待期间用户手势可能过期导致 play 被拒：注册一次性手势恢复
        await video.play().catch(() => {
          const resume = (): void => {
            void video.play().catch(() => undefined);
          };
          window.addEventListener("click", resume, { once: true });
          window.addEventListener("keydown", resume, { once: true });
        });

        const landmarker = await ensureLandmarker();
        machineRef.current = new AttentionStateMachine();
        aggregatorRef.current.reset();
        lastSampleAtRef.current = performance.now();
        loop(video, landmarker);
      } catch (caught) {
        const message =
          caught instanceof Error ? caught.message : "学习状态感知启动失败";
        runningRef.current = false;
        setStatus((prev) => ({ ...IDLE_STATUS, error: message }));
        throw caught instanceof Error ? caught : new Error(message);
      }
    },
    [ensureLandmarker, loop]
  );

  return { status, start, stop };
}
