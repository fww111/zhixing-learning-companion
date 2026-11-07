import { useEffect, useRef, useState } from "react";
import { Code2, Eye, EyeOff, Video, VideoOff, Wand2 } from "lucide-react";
import type { AttentionStateKey } from "../composables/attentionInference";
import { useAttentionAnalysis, type AttentionSample } from "../composables/useAttentionAnalysis";
import {
  decideIntervention,
  interventionCopy,
  loadAttentionThresholds,
  type CodeFailureRecord,
  type InterventionKind
} from "../composables/attentionInterventionModel";
import { setSharedAttention } from "../state/attentionShared";
import { createLearningProfileEvent } from "../api/client";

/** 代码实验运行失败广播事件名（KnowledgeLearningPage / AssessmentPanel 在 runCode 失败时派发） */
export const CODE_RUN_FAILED_EVENT = "pla_code_run_failed";

const STATE_LABELS: Record<AttentionStateKey, string> = {
  focused: "专注中",
  confused: "似乎有点困惑",
  distracted: "走神啦",
  tired: "看起来累了",
  no_face: "未检测到人脸"
};

const STATE_CLASS: Record<AttentionStateKey, string> = {
  focused: "ok",
  confused: "warn",
  distracted: "warn",
  tired: "warn",
  no_face: "idle"
};

const SAMPLE_INTERVAL_MS = 10_000;

export interface AttentionFloatingProps {
  token: string | undefined;
  activeCourseId?: number;
  /** 当前知识点 id（仅知识点学习页存在），用于采样事件与介入去重 */
  nodeId: string;
  topic: string;
  /** 用户点击"让 AI 换种讲法"时触发（由 AppLayout 打开辅导窗并携带上下文） */
  onIntervene?: (context: { nodeId: string; topic: string; state: AttentionStateKey; codeError?: string; highConfidence?: boolean }) => void;
}

/**
 * 全局学习状态感知悬浮窗（issue #14/#15）：
 * - 摄像头在会话内持续开启（跨页面），左下角常驻，与智能辅导悬浮窗分居两侧
 * - confused 持续 ≥15s（可配置）弹介入卡片；代码实验连续失败 × 困惑 → 高置信提前介入
 * - distracted 持续 ≥20s 温和提醒（不调起辅导、不模态、独立冷却）
 * - 同一知识点最多介入 2 次（防打扰），阈值可经 localStorage（pla_attention_thresholds）覆盖便于演示
 * - 每 10s 上报聚合采样（attention_sample 画像事件，仅 JSON 指标）
 * - 隐私：画面仅本机推理，绝不离开浏览器
 */
export function AttentionFloating({ token, activeCourseId, nodeId, topic, onIntervene }: AttentionFloatingProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [gentleHint, setGentleHint] = useState(false);
  const [intervention, setIntervention] = useState<InterventionKind>("none");
  const attention = useAttentionAnalysis({
    sampleIntervalMs: SAMPLE_INTERVAL_MS,
    onSample: (sample: AttentionSample) => {
      void (async () => {
        if (!Number.isFinite(activeCourseId) || !nodeId) return;
        try {
          await createLearningProfileEvent(token, activeCourseId as number, {
            event_type: "attention_sample",
            topic,
            knowledge_node_id: nodeId,
            detail: `${topic}: 专注度采样（主导状态 ${sample.dominant}）`,
            event_payload: { ...sample },
            evidence_strength: "weak"
          });
        } catch {
          // 感知上报失败绝不阻塞学习主流程
        }
      })();
    }
  });
  const attentionStopRef = useRef(attention.stop);
  attentionStopRef.current = attention.stop;

  const thresholdsRef = useRef(loadAttentionThresholds());
  const stateSinceRef = useRef<number>(Date.now());
  const lastStateRef = useRef<AttentionStateKey | "">("");
  const nodeInterventionsRef = useRef<Map<string, number>>(new Map());
  const codeFailuresRef = useRef<CodeFailureRecord[]>([]);
  const lastCodeErrorRef = useRef<string | undefined>(undefined);
  const gentleLastAtRef = useRef(0);
  const gentleTimerRef = useRef<number | null>(null);
  const interveneContextRef = useRef<{
    nodeId: string;
    topic: string;
    state: AttentionStateKey;
    codeError?: string;
    highConfidence?: boolean;
  } | null>(null);

  // 双信号：监听代码实验运行失败广播（窗口内 ≥2 次 × 困惑 → 高置信介入）
  useEffect(() => {
    function handleCodeFailure(event: Event) {
      const detail = (event as CustomEvent<{ summary?: string }>).detail || {};
      const summary = (detail.summary || "代码运行失败").slice(0, 120);
      codeFailuresRef.current = [...codeFailuresRef.current, { at: Date.now(), summary }].slice(-20);
      lastCodeErrorRef.current = summary;
    }
    window.addEventListener(CODE_RUN_FAILED_EVENT, handleCodeFailure);
    return () => window.removeEventListener(CODE_RUN_FAILED_EVENT, handleCodeFailure);
  }, []);

  useEffect(() => () => {
    if (gentleTimerRef.current !== null) {
      window.clearTimeout(gentleTimerRef.current);
    }
  }, []);

  // 状态写入共享 store（辅导请求读取），并按决策模型触发介入/温和提醒
  useEffect(() => {
    if (!enabled) {
      setSharedAttention(null);
      stateSinceRef.current = Date.now();
      lastStateRef.current = "";
      setIntervention("none");
      setGentleHint(false);
      return;
    }
    const now = Date.now();
    const { state, confidence } = attention.status;
    setSharedAttention({
      state,
      confidence,
      courseId: Number.isFinite(activeCourseId) ? activeCourseId : undefined,
      nodeId,
      updatedAt: now
    });

    // 宽限设计：真实表情有抖动（短暂回专注/丢脸），2.5s 内恢复原状态不清零累计
    if (state !== lastStateRef.current) {
      const hadPrevious = lastStateRef.current !== "";
      lastStateRef.current = state;
      if (hadPrevious && state !== "focused") {
        // 从 A 状态抖到 B 再回 A：保留 2.5s 宽限
        // （实现上简化为：状态切换即重置计时；真实抖动由 inference 层状态机平滑）
      }
      stateSinceRef.current = now;
    }

    const decision = decideIntervention({
      thresholds: thresholdsRef.current,
      state,
      heldMs: now - stateSinceRef.current,
      nodeCount: nodeInterventionsRef.current.get(nodeId) ?? 0,
      codeFailures: codeFailuresRef.current,
      now,
      lastGentleAt: gentleLastAtRef.current
    });

    if (decision.kind === "high_confidence" || decision.kind === "standard") {
      nodeInterventionsRef.current.set(nodeId, (nodeInterventionsRef.current.get(nodeId) ?? 0) + 1);
      stateSinceRef.current = now; // 介入后重新计时，避免连续弹
      interveneContextRef.current = {
        nodeId,
        topic,
        state,
        codeError: decision.lastError,
        highConfidence: decision.kind === "high_confidence"
      };
      setIntervention(decision.kind);
      setGentleHint(false);
    } else if (decision.kind === "gentle") {
      gentleLastAtRef.current = now;
      setGentleHint(true);
      if (gentleTimerRef.current !== null) {
        window.clearTimeout(gentleTimerRef.current);
      }
      gentleTimerRef.current = window.setTimeout(() => setGentleHint(false), 6000);
    } else if (state === "focused" || state === "no_face") {
      setIntervention("none");
      setGentleHint(false);
    }
  }, [attention.status, enabled, activeCourseId, nodeId, topic]);

  useEffect(
    () => () => {
      attentionStopRef.current();
    },
    []
  );

  async function handleEnable() {
    if (!videoRef.current) return;
    setBusy(true);
    setEnabled(true);
    stateSinceRef.current = Date.now();
    try {
      await attention.start(videoRef.current);
    } catch {
      // 失败保持卡片展开：错误信息（如拒绝授权）显示在卡片内，用户可关闭或重试
    } finally {
      setBusy(false);
    }
  }

  function handleDisable() {
    attentionStopRef.current();
    setEnabled(false);
    setIntervention("none");
    setGentleHint(false);
  }

  function handleIntervene() {
    const context = interveneContextRef.current;
    setIntervention("none");
    if (context) {
      onIntervene?.(context);
    }
  }

  const copy = intervention === "standard" || intervention === "high_confidence"
    ? interventionCopy(intervention, topic, lastCodeErrorRef.current)
    : null;

  return (
    <aside className="attention-card" aria-label="学习状态感知">
      <div className="attention-card-head">
        <span className={`attention-breath-ring ${STATE_CLASS[attention.status.state]} ${enabled ? "on" : ""}`} aria-hidden="true">
          <i />
        </span>
        <strong>学习状态感知</strong>
        {enabled ? (
          <button className="attention-toggle on" disabled={busy} onClick={handleDisable} type="button">
            <VideoOff size={14} />
            关闭
          </button>
        ) : (
          <button className="attention-toggle" disabled={busy} onClick={() => { void handleEnable(); }} type="button">
            <Video size={14} />
            开启
          </button>
        )}
      </div>

      {/* video 元素始终是同一个（仅 CSS 显隐）：React 重建元素会导致摄像头流丢失 */}
      <div className={enabled ? "attention-body" : "attention-body hidden-body"}>
        <video className={`attention-preview${enabled ? "" : " hidden-preview"}`} muted playsInline ref={videoRef} />
        {enabled ? (
          <div className="attention-meta">
            <span className={`attention-state ${STATE_CLASS[attention.status.state]}`}>
              {STATE_LABELS[attention.status.state]}
            </span>
            {attention.status.confidence > 0 ? (
              <small>置信度 {Math.round(attention.status.confidence * 100)}%</small>
            ) : null}
            {attention.status.blinkRatePerMinute > 0 ? (
              <small>眨眼 {attention.status.blinkRatePerMinute}/min</small>
            ) : null}
            {busy ? <small>模型加载中…</small> : null}
            {attention.status.error ? <small className="attention-error">{attention.status.error}</small> : null}
            <small className="attention-privacy">
              <EyeOff size={11} /> 仅本机分析，画面不上传
            </small>
          </div>
        ) : (
          <p className="attention-hint">
            开启后在本机分析摄像头画面（专注/困惑/走神/疲劳），辅助 AI 在你卡住时主动换一种讲法。
            画面不会离开你的电脑。
          </p>
        )}
      </div>

      {gentleHint ? (
        <div className="attention-gentle-hint">
          <Eye size={13} />
          <span>走神了一会儿？回来继续「{topic || "当前知识点"}」呀。</span>
        </div>
      ) : null}

      {copy ? (
        <div className="attention-fullscreen-intervention" role="dialog" aria-label="AI 主动介入">
          <div className="afi-backdrop" aria-hidden="true" />
          <div className="afi-card">
            <span className="afi-orb" aria-hidden="true" />
            <p className="afi-eyebrow">
              {intervention === "high_confidence" ? "代码连续失败 × 状态困惑" : "AI 老师注意到你了"}
            </p>
            <h3>{copy.title}</h3>
            <p className="afi-body">{copy.body}</p>
            <div className="afi-actions">
              <button className="primary-action" onClick={handleIntervene} type="button">
                <Wand2 size={16} />
                {intervention === "high_confidence" ? "让 AI 帮我看看代码" : "换种讲法"}
              </button>
              <button className="secondary-action" onClick={() => setIntervention("none")} type="button">
                我自己再想想
              </button>
            </div>
            <small className="afi-privacy">画面仅在本机分析，AI 只收到状态信号</small>
          </div>
        </div>
      ) : null}
    </aside>
  );
}
