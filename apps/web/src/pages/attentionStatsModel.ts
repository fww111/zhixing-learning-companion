import type { LearningProfileEvent } from "../api/client";

export type AttentionStateKey = "focused" | "confused" | "distracted" | "tired" | "no_face";

export interface AttentionStats {
  total: number;
  focused: number;
  confused: number;
  distracted: number;
  tired: number;
  noFace: number;
  /** 专注占比 0-100（无样本为 null） */
  focusedPercent: number | null;
  /** 困惑占比 0-100（无样本为 null）；越高说明知识点越卡 */
  confusedPercent: number | null;
  /** 困惑样本数达到分析门槛的最少样本数 */
  minSamplesForInsight: number;
  /** 是否值得在评估页提示"该知识点可能偏难" */
  confusedSignal: boolean;
  /** 最近一次采样时间（ISO），无样本为空 */
  lastSampleAt: string;
  /** 采样覆盖的知识点列表（最多 6 个） */
  topics: string[];
}

const MIN_SAMPLES_FOR_INSIGHT = 5;
/** 困惑占比超过该值（且样本达标）视为"该知识点可能偏难"信号 */
const CONFUSED_SIGNAL_PERCENT = 30;

const STATE_KEYS: AttentionStateKey[] = ["focused", "confused", "distracted", "tired", "no_face"];

/**
 * 聚合 attention_sample 画像事件为专注度分析（issue #15 评估维度）。
 * 采样事件由 AttentionFloating 每 10s 落库，event_payload 含 dominant 状态。
 */
export function buildAttentionStats(events: LearningProfileEvent[]): AttentionStats {
  const counts: Record<AttentionStateKey, number> = { focused: 0, confused: 0, distracted: 0, tired: 0, no_face: 0 };
  const topics = new Set<string>();
  let total = 0;
  let lastSampleAt = "";

  for (const event of events) {
    if (event.event_type !== "attention_sample") {
      continue;
    }
    const payload = event.event_payload as Record<string, unknown> | undefined;
    const dominant = typeof payload?.dominant === "string" ? (payload.dominant as AttentionStateKey) : undefined;
    if (!dominant || !STATE_KEYS.includes(dominant)) {
      continue;
    }
    counts[dominant] += 1;
    total += 1;
    if (event.topic) {
      topics.add(event.topic);
    }
    if (event.created_at > lastSampleAt) {
      lastSampleAt = event.created_at;
    }
  }

  const focusedPercent = total ? Math.round((counts.focused / total) * 100) : null;
  const confusedPercent = total ? Math.round((counts.confused / total) * 100) : null;
  return {
    total,
    focused: counts.focused,
    confused: counts.confused,
    distracted: counts.distracted,
    tired: counts.tired,
    noFace: counts.no_face,
    focusedPercent,
    confusedPercent,
    minSamplesForInsight: MIN_SAMPLES_FOR_INSIGHT,
    confusedSignal: Boolean(
      total >= MIN_SAMPLES_FOR_INSIGHT && confusedPercent !== null && confusedPercent >= CONFUSED_SIGNAL_PERCENT
    ),
    lastSampleAt,
    topics: [...topics].slice(0, 6)
  };
}

export const ATTENTION_STATE_LABELS: Record<AttentionStateKey, string> = {
  focused: "专注",
  confused: "困惑",
  distracted: "走神",
  tired: "疲劳",
  no_face: "离席"
};
