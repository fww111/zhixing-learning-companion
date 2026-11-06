import { useEffect, useRef, useState } from "react";
import { Eye, EyeOff, Video, VideoOff, Wand2 } from "lucide-react";
import type { AttentionStateKey } from "../composables/attentionInference";
import { useAttentionAnalysis, type AttentionSample } from "../composables/useAttentionAnalysis";
import { setSharedAttention } from "../state/attentionShared";
import { createLearningProfileEvent } from "../api/client";

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

/** 困惑持续多久触发主动介入（issue #15）；同一知识点最多介入次数 */
const CONFUSED_INTERVENTION_MS = 10_000;
const MAX_INTERVENTIONS_PER_NODE = 2;
const SAMPLE_INTERVAL_MS = 10_000;

export interface AttentionFloatingProps {
  token: string | undefined;
  activeCourseId?: number;
  /** 当前知识点 id（仅知识点学习页存在），用于采样事件与介入去重 */
  nodeId: string;
  topic: string;
  /** 用户点击"让 AI 换种讲法"时触发（由 AppLayout 打开辅导窗并携带上下文） */
  onIntervene?: (context: { nodeId: string; topic: string; state: AttentionStateKey }) => void;
}

/**
 * 全局学习状态感知悬浮窗（issue #14/#15）：
 * - 摄像头在会话内持续开启（跨页面），左下角常驻，与智能辅导悬浮窗分居两侧
 * - confused 持续 ≥15s 时展示介入横幅，一键让辅导 AI 换种讲法
 * - 每 10s 上报聚合采样（attention_sample 画像事件，仅 JSON 指标）
 * - 隐私：画面仅本机推理，绝不离开浏览器
 */
export function AttentionFloating({ token, activeCourseId, nodeId, topic, onIntervene }: AttentionFloatingProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
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

  const [intervention, setIntervention] = useState(false);
  const confusedSinceRef = useRef<number | null>(null);
  const interventionsByNodeRef = useRef<Map<string, number>>(new Map());
  const interveneContextRef = useRef<{ nodeId: string; topic: string; state: AttentionStateKey } | null>(null);

  // 状态写入共享 store（辅导请求读取），并跟踪 confused 持续时长触发介入
  useEffect(() => {
    if (!enabled) {
      setSharedAttention(null);
      confusedSinceRef.current = null;
      setIntervention(false);
      return;
    }
    const { state, confidence } = attention.status;
    setSharedAttention({
      state,
      confidence,
      courseId: Number.isFinite(activeCourseId) ? activeCourseId : undefined,
      nodeId,
      updatedAt: Date.now()
    });

    if (state === "confused") {
      if (confusedSinceRef.current === null) {
        confusedSinceRef.current = Date.now();
      }
      const heldMs = Date.now() - confusedSinceRef.current;
      const used = interventionsByNodeRef.current.get(nodeId) ?? 0;
      if (heldMs >= CONFUSED_INTERVENTION_MS && used < MAX_INTERVENTIONS_PER_NODE && nodeId) {
        interventionsByNodeRef.current.set(nodeId, used + 1);
        confusedSinceRef.current = Date.now(); // 介入后重新计时，避免连续弹
        interveneContextRef.current = { nodeId, topic, state };
        setIntervention(true);
      }
    } else {
      // 宽限设计：真实表情有抖动（短暂回专注/丢脸），2.5s 内恢复困惑不清零累计
      if (confusedSinceRef.current !== null && Date.now() - confusedSinceRef.current > 2500) {
        confusedSinceRef.current = null;
      }
      setIntervention(false);
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
    setIntervention(false);
  }

  function handleIntervene() {
    const context = interveneContextRef.current;
    setIntervention(false);
    if (context) {
      onIntervene?.(context);
    }
  }

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

      {intervention ? (
        <button className="attention-intervention" onClick={handleIntervene} type="button">
          <Wand2 size={13} />
          看起来这一段有点难？让 AI 换种讲法
        </button>
      ) : null}

      {intervention ? (
        <div className="attention-fullscreen-intervention" role="dialog" aria-label="AI 主动介入">
          <div className="afi-backdrop" aria-hidden="true" />
          <div className="afi-card">
            <span className="afi-orb" aria-hidden="true" />
            <p className="afi-eyebrow">AI 老师注意到你了</p>
            <h3>这一段可能有点难？</h3>
            <p className="afi-body">
              你在「{topic || "当前知识点"}」上已经困惑了一会儿。我可以结合课程知识库，
              先用一个直觉类比、再给一个可运行的例子，换一种讲法。
            </p>
            <div className="afi-actions">
              <button className="primary-action" onClick={handleIntervene} type="button">
                <Wand2 size={16} />
                换种讲法
              </button>
              <button className="secondary-action" onClick={() => setIntervention(false)} type="button">
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
