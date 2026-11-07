/**
 * 学习状态感知的介入规则模型（issue #15）。
 *
 * 纯函数决策，不触碰 DOM/网络：
 * - confused 持续 ≥ confusedMs（默认 15s，可配置）→ 标准介入（弹卡片，可调起辅导换种讲法）
 * - 代码实验 5 分钟窗口内 ≥2 次运行失败 且 当前 confused → 高置信介入（不等满 15s，文案带"帮你看看代码"）
 * - distracted 持续 ≥ distractedMs（默认 20s）→ 温和提醒（不调起辅导，不模态）
 * - 防打扰：同一知识点标准/高置信介入每窗口最多 maxPerNode 次；温和提醒独立限频 gentleCooldownMs
 *
 * 阈值从 localStorage（pla_attention_thresholds）读取，便于演示时调低。
 */

import type { AttentionStateKey } from "./attentionInference";

export interface AttentionThresholds {
  /** confused 持续多久触发标准介入（毫秒），默认 15000 */
  confusedMs: number;
  /** distracted 持续多久触发温和提醒（毫秒），默认 20000 */
  distractedMs: number;
  /** 同一知识点介入上限（标准+高置信合计），默认 2 */
  maxPerNode: number;
  /** 代码失败统计窗口（毫秒），默认 5 分钟 */
  codeFailureWindowMs: number;
  /** 窗口内多少次代码失败判定为"连续失败"，默认 2 */
  codeFailureThreshold: number;
  /** 温和提醒冷却（毫秒），默认 3 分钟 */
  gentleCooldownMs: number;
}

export const DEFAULT_ATTENTION_THRESHOLDS: AttentionThresholds = {
  confusedMs: 15_000,
  distractedMs: 20_000,
  maxPerNode: 2,
  codeFailureWindowMs: 5 * 60_000,
  codeFailureThreshold: 2,
  gentleCooldownMs: 3 * 60_000
};

const STORAGE_KEY = "pla_attention_thresholds";

export function loadAttentionThresholds(storage: Pick<Storage, "getItem"> = localStorage): AttentionThresholds {
  let raw: string | null = null;
  try {
    raw = storage.getItem(STORAGE_KEY);
  } catch {
    return { ...DEFAULT_ATTENTION_THRESHOLDS };
  }
  if (!raw) {
    return { ...DEFAULT_ATTENTION_THRESHOLDS };
  }
  return sanitizeThresholds(parseJson(raw));
}

export function saveAttentionThresholds(
  thresholds: Partial<AttentionThresholds>,
  storage: Pick<Storage, "getItem" | "setItem"> = localStorage
): AttentionThresholds {
  const merged = sanitizeThresholds({ ...loadAttentionThresholds(storage), ...thresholds });
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(merged));
  } catch {
    // 隐私模式等写入失败不阻塞主流程
  }
  return merged;
}

function parseJson(raw: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function sanitizeThresholds(value: Record<string, unknown>): AttentionThresholds {
  const numberBetween = (key: keyof AttentionThresholds, min: number, max: number, fallback: number): number => {
    const raw = value[key];
    if (typeof raw === "number" && Number.isFinite(raw) && raw >= min && raw <= max) {
      return raw;
    }
    return fallback;
  };
  return {
    confusedMs: numberBetween("confusedMs", 3_000, 120_000, DEFAULT_ATTENTION_THRESHOLDS.confusedMs),
    distractedMs: numberBetween("distractedMs", 5_000, 180_000, DEFAULT_ATTENTION_THRESHOLDS.distractedMs),
    maxPerNode: numberBetween("maxPerNode", 1, 10, DEFAULT_ATTENTION_THRESHOLDS.maxPerNode),
    codeFailureWindowMs: numberBetween("codeFailureWindowMs", 30_000, 30 * 60_000, DEFAULT_ATTENTION_THRESHOLDS.codeFailureWindowMs),
    codeFailureThreshold: numberBetween("codeFailureThreshold", 1, 10, DEFAULT_ATTENTION_THRESHOLDS.codeFailureThreshold),
    gentleCooldownMs: numberBetween("gentleCooldownMs", 30_000, 30 * 60_000, DEFAULT_ATTENTION_THRESHOLDS.gentleCooldownMs)
  };
}

export type InterventionKind = "none" | "gentle" | "standard" | "high_confidence";

export interface InterventionDecision {
  kind: InterventionKind;
  /** 触发原因（用于介入卡片文案与埋点） */
  reason: string;
  /** 代码场景：最近一次失败摘要，供辅导上下文 */
  lastError?: string;
}

export interface CodeFailureRecord {
  at: number;
  summary: string;
}

/** 代码失败时间窗过滤：只保留 window 内的记录。 */
export function recentCodeFailures(records: CodeFailureRecord[], now: number, windowMs: number): CodeFailureRecord[] {
  return records.filter((record) => now - record.at <= windowMs);
}

/**
 * 介入决策核心。
 *
 * @param state        当前主导状态
 * @param heldMs       当前状态已持续毫秒数（状态机切换时归零，由调用方维护）
 * @param nodeCount    当前知识点已用介入次数（标准+高置信）
 * @param codeFailures 代码失败记录（全量，内部做窗口过滤）
 * @param now          当前时间戳
 * @param lastGentleAt 上次温和提醒时间戳（0 表示从未）
 */
export function decideIntervention(input: {
  thresholds?: AttentionThresholds;
  state: AttentionStateKey;
  heldMs: number;
  nodeCount: number;
  codeFailures: CodeFailureRecord[];
  now: number;
  lastGentleAt?: number;
  hasNodeId?: boolean;
}): InterventionDecision {
  const thresholds = input.thresholds ?? DEFAULT_ATTENTION_THRESHOLDS;
  const failures = recentCodeFailures(input.codeFailures, input.now, thresholds.codeFailureWindowMs);
  const lastError = failures.length ? failures[failures.length - 1]!.summary : undefined;

  // 高置信：代码连续失败 × 困惑同时出现（不等满 confusedMs，但至少要有一些困惑信号）
  const confusedEnough = input.state === "confused" && input.heldMs >= Math.min(4_000, thresholds.confusedMs);
  if (confusedEnough && failures.length >= thresholds.codeFailureThreshold) {
    if (input.nodeCount >= thresholds.maxPerNode) {
      return { kind: "none", reason: "代码失败+困惑命中但该知识点介入次数已达上限" };
    }
    return {
      kind: "high_confidence",
      reason: `代码实验 ${failures.length} 次未通过且处于困惑状态`,
      lastError
    };
  }

  // 标准介入：困惑持续达到阈值
  if (input.state === "confused" && input.heldMs >= thresholds.confusedMs) {
    if (input.nodeCount >= thresholds.maxPerNode) {
      return { kind: "none", reason: "困惑持续达标但该知识点介入次数已达上限" };
    }
    return { kind: "standard", reason: `困惑持续 ${Math.round(input.heldMs / 1000)} 秒`, lastError };
  }

  // 温和提醒：走神持续达到阈值，独立冷却，不打断不调起辅导
  if (
    input.state === "distracted" &&
    input.heldMs >= thresholds.distractedMs &&
    input.now - (input.lastGentleAt ?? 0) >= thresholds.gentleCooldownMs
  ) {
    return { kind: "gentle", reason: `走神持续 ${Math.round(input.heldMs / 1000)} 秒` };
  }

  return { kind: "none", reason: "" };
}

/** 介入卡文案：区分普通困惑与代码场景。 */
export function interventionCopy(kind: Exclude<InterventionKind, "none">, topic: string, lastCodeError?: string): { title: string; body: string } {
  if (kind === "gentle") {
    return {
      title: "回来继续呀",
      body: `走神了一会儿？我们正在学「${topic || "当前知识点"}」，回来接着看。`
    };
  }
  if (kind === "high_confidence") {
    return {
      title: "代码连续没跑通？让 AI 帮你看看",
      body: `你在「${topic || "当前知识点"}」的代码实验连续失败${lastCodeError ? `（最近错误：${lastCodeError}）` : ""}，同时看起来有些困惑。AI 可以结合课程知识库帮你定位问题、换种讲法。`
    };
  }
  return {
    title: "这一段可能有点难？",
    body: `你在「${topic || "当前知识点"}」上已经困惑了一会儿。AI 可以结合课程知识库，先用直觉类比、再给可运行的例子，换一种讲法。`
  };
}
