/**
 * 学习专注度推理：纯逻辑模块（不依赖 MediaPipe / DOM，可被 tsx 单测直接驱动）。
 *
 * 信号来源是 MediaPipe FaceLandmarker 的输出（blendshapes + 头部变换矩阵），
 * 本模块负责三件事：
 *  1. extractFaceSignals：把 blendshapes 类别数组转换为帧级信号；
 *  2. AttentionStateMachine：帧信号 → 学习状态（focused/confused/distracted/tired/no_face），
 *     带候选确认窗口（状态需持续一段时间才切换，防抖）；
 *  3. AttentionWindowAggregator：滑动窗口内的状态时长占比聚合，用于每 10s 上报一次的
 *     attention_sample 画像事件。
 *
 * 隐私约束：本模块只处理数值信号，任何视频帧都不会离开浏览器。
 */

export type AttentionStateKey = "focused" | "confused" | "distracted" | "tired" | "no_face";

export interface FaceFrameSignals {
  hasFace: boolean;
  /** 皱眉强度 0..1（browDown* + browInnerUp 加权），困惑的核心信号 */
  browFurrow: number;
  /** 眯眼 0..1（eyeSquint*） */
  squint: number;
  /** 视线水平偏移 -1..1（eyeLookIn/Out* 均值，正为向右） */
  gazeX: number;
  /** 视线垂直偏移 -1..1（正为向下看） */
  gazeY: number;
  /** 头部偏航角（度，绝对值用于走神判定） */
  yawDeg: number;
  /** 头部俯仰角（度，符号约定取决于矩阵；判定时取绝对值） */
  pitchDeg: number;
  /** 双眼闭合程度 0..1 */
  blinkBoth: number;
  timestampMs: number;
}

export interface AttentionThresholds {
  /** 困惑：皱眉阈值 */
  confusedBrowFurrow: number;
  /** 困惑：眯眼阈值（与皱眉同时满足的第二路径） */
  confusedSquint: number;
  /** 困惑候选需持续的毫秒数 */
  confusedConfirmMs: number;
  /** 走神：视线水平/垂直偏移阈值 */
  distractedGazeX: number;
  distractedGazeY: number;
  /** 走神：头部偏航阈值（度） */
  distractedYawDeg: number;
  distractedConfirmMs: number;
  /** 疲劳：单次闭眼持续毫秒数（超过视为长闭眼） */
  tiredLongBlinkMs: number;
  /** 疲劳候选需持续的毫秒数 */
  tiredConfirmMs: number;
  /** 无脸候选需持续的毫秒数 */
  noFaceConfirmMs: number;
  /** 回到专注需持续的毫秒数 */
  focusedConfirmMs: number;
}

export const DEFAULT_ATTENTION_THRESHOLDS: AttentionThresholds = {
  confusedBrowFurrow: 0.3,
  confusedSquint: 0.18,
  confusedConfirmMs: 3000,
  distractedGazeX: 0.45,
  distractedGazeY: 0.5,
  distractedYawDeg: 22,
  distractedConfirmMs: 2200,
  tiredLongBlinkMs: 600,
  tiredConfirmMs: 8000,
  noFaceConfirmMs: 3000,
  focusedConfirmMs: 1200
};

type BlendshapeLike = { categoryName?: string; displayName?: string; score: number };

function meanOf(categories: Map<string, number>, names: string[]): number {
  let sum = 0;
  for (const name of names) {
    sum += categories.get(name) ?? 0;
  }
  return sum / names.length;
}

/**
 * 把 MediaPipe blendshapes 类别 + 头部变换矩阵（column-major 4x4）转为帧级信号。
 * 欧拉角近似：yaw=atan2(r02,r22)、pitch=asin(-r12)、roll=atan2(r10,r11)；
 * MediaPipe 的矩阵朝向约定下符号可能与直觉相反，因此状态机只使用绝对值/对称阈值。
 */
export function extractFaceSignals(
  blendshapes: BlendshapeLike[],
  transformationMatrix: number[] | undefined,
  timestampMs: number
): FaceFrameSignals {
  const categories = new Map<string, number>();
  for (const item of blendshapes) {
    const name = item.categoryName || item.displayName || "";
    categories.set(name, item.score);
  }

  let yawDeg = 0;
  let pitchDeg = 0;
  let rollDeg = 0;
  if (transformationMatrix && transformationMatrix.length >= 16) {
    // column-major: r[C*4+R]
    const r = (row: number, col: number): number => transformationMatrix[col * 4 + row];
    yawDeg = (Math.atan2(r(0, 2), r(2, 2)) * 180) / Math.PI;
    const sinP = Math.max(-1, Math.min(1, -r(1, 2)));
    pitchDeg = (Math.asin(sinP) * 180) / Math.PI;
    rollDeg = (Math.atan2(r(1, 0), r(1, 1)) * 180) / Math.PI;
  }

  const blinkLeft = categories.get("eyeBlinkLeft") ?? 0;
  const blinkRight = categories.get("eyeBlinkRight") ?? 0;

  return {
    hasFace: blendshapes.length > 0,
    browFurrow:
      meanOf(categories, ["browDownLeft", "browDownRight"]) * 0.85 +
      (categories.get("browInnerUp") ?? 0) * 0.3,
    squint: meanOf(categories, ["eyeSquintLeft", "eyeSquintRight"]),
    // MediaPipe 命名：In=朝鼻子、Out=朝耳朵；看右 = InLeft+OutRight 高，看左 = OutLeft+InRight 高
    gazeX:
      meanOf(categories, ["eyeLookInLeft", "eyeLookOutRight"]) -
      meanOf(categories, ["eyeLookOutLeft", "eyeLookInRight"]),
    gazeY: meanOf(categories, ["eyeLookDownLeft", "eyeLookDownRight"]) -
      meanOf(categories, ["eyeLookUpLeft", "eyeLookUpRight"]),
    yawDeg,
    pitchDeg,
    blinkBoth: (blinkLeft + blinkRight) / 2,
    timestampMs
  };
}

export interface AttentionStateSnapshot {
  state: AttentionStateKey;
  confidence: number;
  /** 当前状态自该时刻起持续（ms） */
  sinceMs: number;
}

interface CandidateRuleResult {
  state: AttentionStateKey;
}

/**
 * 学习状态机：候选状态需持续各自 confirm 窗口才真正切换，避免眨眼/瞬时表情抖动。
 * 眨眼的长闭眼检测在内部完成（跟踪闭眼起止），供 tired 判定使用。
 */
export class AttentionStateMachine {
  readonly thresholds: AttentionThresholds;

  private state: AttentionStateKey = "no_face";
  private stateSinceMs = 0;
  private candidate: AttentionStateKey = "no_face";
  private candidateSinceMs = 0;

  private eyesClosed = false;
  private eyesClosedSinceMs = 0;
  private longBlinkSeenAtMs = 0;
  private windowFirstMs = 0;
  private windowBlinkCount = 0;

  constructor(thresholds?: Partial<AttentionThresholds>) {
    this.thresholds = { ...DEFAULT_ATTENTION_THRESHOLDS, ...thresholds };
  }

  /** 最近 60s 眨眼频率（次/分钟），供疲劳判定与调试面板使用 */
  blinkRatePerMinute(nowMs: number): number {
    if (!this.windowFirstMs) return 0;
    const spanMs = Math.max(1, nowMs - this.windowFirstMs);
    return (this.windowBlinkCount * 60000) / spanMs;
  }

  update(signal: FaceFrameSignals): AttentionStateSnapshot {
    const nowMs = signal.timestampMs;
    this.trackBlinks(signal, nowMs);

    let immediate: CandidateRuleResult;
    if (!signal.hasFace) {
      immediate = { state: "no_face" };
    } else if (nowMs - this.longBlinkSeenAtMs <= 1500) {
      immediate = { state: "tired" };
    } else if (this.isDistracted(signal)) {
      immediate = { state: "distracted" };
    } else if (this.isConfused(signal)) {
      immediate = { state: "confused" };
    } else {
      immediate = { state: "focused" };
    }

    if (immediate.state !== this.candidate) {
      this.candidate = immediate.state;
      this.candidateSinceMs = nowMs;
    }

    const confirmMs = this.confirmMsFor(immediate.state);
    const candidateHeld = nowMs - this.candidateSinceMs >= confirmMs;
    if (candidateHeld && immediate.state !== this.state) {
      this.state = immediate.state;
      this.stateSinceMs = nowMs;
    }

    return {
      state: this.state,
      confidence: this.confidenceFor(nowMs),
      sinceMs: this.stateSinceMs
    };
  }

  private confirmMsFor(state: AttentionStateKey): number {
    const t = this.thresholds;
    if (state === "confused") return t.confusedConfirmMs;
    if (state === "distracted") return t.distractedConfirmMs;
    if (state === "tired") return t.tiredConfirmMs;
    if (state === "no_face") return t.noFaceConfirmMs;
    return t.focusedConfirmMs;
  }

  private confidenceFor(nowMs: number): number {
    const heldMs = Math.max(0, nowMs - this.stateSinceMs);
    const confirmMs = Math.max(1, this.confirmMsFor(this.state));
    return Math.round(Math.min(0.95, 0.55 + (heldMs / confirmMs) * 0.4) * 100) / 100;
  }

  private trackBlinks(signal: FaceFrameSignals, nowMs: number): void {
    if (!this.windowFirstMs) {
      this.windowFirstMs = nowMs;
    }
    const closed = signal.hasFace && signal.blinkBoth >= 0.5;
    if (closed && !this.eyesClosed) {
      this.eyesClosed = true;
      this.eyesClosedSinceMs = nowMs;
      this.windowBlinkCount += 1;
    } else if (!closed && this.eyesClosed) {
      this.eyesClosed = false;
      if (nowMs - this.eyesClosedSinceMs >= this.thresholds.tiredLongBlinkMs) {
        this.longBlinkSeenAtMs = nowMs;
      }
    }
    // 眨眼窗口保留最近 90s，防止计数无限增长
    if (nowMs - this.windowFirstMs > 90000) {
      this.windowFirstMs = nowMs;
      this.windowBlinkCount = Math.max(0, this.windowBlinkCount - 1);
    }
  }

  private isConfused(signal: FaceFrameSignals): boolean {
    const t = this.thresholds;
    return (
      signal.browFurrow >= t.confusedBrowFurrow ||
      (signal.browFurrow >= t.confusedBrowFurrow * 0.8 && signal.squint >= t.confusedSquint)
    );
  }

  private isDistracted(signal: FaceFrameSignals): boolean {
    const t = this.thresholds;
    return (
      Math.abs(signal.gazeX) >= t.distractedGazeX ||
      Math.abs(signal.gazeY) >= t.distractedGazeY ||
      Math.abs(signal.yawDeg) >= t.distractedYawDeg
    );
  }
}

interface AggregatedSegment {
  fromMs: number;
  toMs: number;
  state: AttentionStateKey;
}

/** 滑动窗口状态占比聚合：按状态持续时间计算分布（不是按帧数采样）。 */
export class AttentionWindowAggregator {
  private segments: AggregatedSegment[] = [];
  private currentState: AttentionStateKey | null = null;
  private segmentStartMs = 0;

  push(state: AttentionStateKey, timestampMs: number): void {
    if (this.currentState === null) {
      this.currentState = state;
      this.segmentStartMs = timestampMs;
      return;
    }
    if (state !== this.currentState) {
      this.segments.push({ fromMs: this.segmentStartMs, toMs: timestampMs, state: this.currentState });
      this.currentState = state;
      this.segmentStartMs = timestampMs;
    }
  }

  /** 返回最近 windowMs 内各状态时长占比（0..1，四舍五入两位），未覆盖时间为 focused 兜底。 */
  distribution(windowMs = 60000, nowMs?: number): Record<AttentionStateKey, number> {
    const result: Record<AttentionStateKey, number> = {
      focused: 0,
      confused: 0,
      distracted: 0,
      tired: 0,
      no_face: 0
    };
    const openSegments = [...this.segments];
    if (this.currentState !== null) {
      // 尚未闭合的当前段（直到 now）也计入分布
      openSegments.push({ fromMs: this.segmentStartMs, toMs: nowMs ?? this.segmentStartMs, state: this.currentState });
    }
    const lastTs = openSegments.length
      ? openSegments[openSegments.length - 1].toMs
      : this.segmentStartMs;
    const now = nowMs ?? lastTs;
    const from = now - windowMs;
    let covered = 0;
    for (const segment of openSegments) {
      const start = Math.max(segment.fromMs, from);
      const end = Math.min(segment.toMs, now);
      if (end <= start) continue;
      result[segment.state] += end - start;
      covered += end - start;
    }
    // 未被任何已知状态覆盖的窗口时间按 focused 计（启动初期）
    const idle = windowMs - covered;
    if (idle > 0) {
      result.focused += idle;
    }
    let total = 0;
    for (const key of Object.keys(result) as AttentionStateKey[]) {
      total += result[key];
    }
    if (total <= 0) return result;
    for (const key of Object.keys(result) as AttentionStateKey[]) {
      result[key] = Math.round((result[key] / total) * 100) / 100;
    }
    return result;
  }

  dominant(windowMs = 60000, nowMs?: number): AttentionStateKey {
    const distribution = this.distribution(windowMs, nowMs);
    let best: AttentionStateKey = "focused";
    let bestScore = -1;
    for (const key of Object.keys(distribution) as AttentionStateKey[]) {
      if (distribution[key] > bestScore) {
        best = key;
        bestScore = distribution[key];
      }
    }
    return best;
  }

  reset(): void {
    this.segments = [];
    this.currentState = null;
    this.segmentStartMs = 0;
  }
}
