import type { DebugHintResult } from "../api/client";

/** AI 结对调试面板状态机（human-in-the-loop：三级提示逐级解锁）。 */
export type DebugMentorStage = "idle" | "loading" | "ready" | "error";

export interface DebugMentorState {
  stage: DebugMentorStage;
  result?: DebugHintResult;
  /** 当前已解锁的最高提示级（1-3），学生自主决定是否看更多 */
  unlockedLevel: number;
  /** 已应用 AI 修复代码（待重跑沙箱验证） */
  appliedFix?: string;
  error: string;
}

export function initialDebugMentorState(): DebugMentorState {
  return { stage: "idle", unlockedLevel: 0, error: "" };
}

export function debugMentorLoading(state: DebugMentorState): DebugMentorState {
  return { ...state, stage: "loading", error: "" };
}

export function debugMentorReady(state: DebugMentorState, result: DebugHintResult): DebugMentorState {
  return { ...state, stage: "ready", result, unlockedLevel: 1, error: "" };
}

export function debugMentorFailed(state: DebugMentorState, error: string): DebugMentorState {
  return { ...state, stage: "error", error };
}

/** 学生点击"再看一条提示"——最多解锁到 hints.length（≤3）。 */
export function unlockNextHint(state: DebugMentorState): DebugMentorState {
  const max = Math.min(3, state.result?.hints.length ?? 0);
  return { ...state, unlockedLevel: Math.min(max, state.unlockedLevel + 1) };
}

/** 学生应用 Level 3 参考修复代码（填进编辑器，随后重跑沙箱验证）。 */
export function applyAIFix(state: DebugMentorState): { state: DebugMentorState; fixedCode: string } {
  const fixedCode = state.result?.fixed_code || "";
  return { state: { ...state, appliedFix: fixedCode }, fixedCode };
}

const CATEGORY_LABELS: Record<DebugHintResult["error_category"], string> = {
  syntax: "语法错误",
  type: "类型不匹配",
  boundary: "越界/非法访问",
  logic: "逻辑偏差",
  runtime: "运行时错误",
  output: "输出不一致"
};

export function debugCategoryLabel(category: DebugHintResult["error_category"]): string {
  return CATEGORY_LABELS[category] ?? "未分类";
}

/** 是否应该展示"应用 AI 修复"按钮：有参考修复代码且尚未应用。 */
export function canApplyFix(state: DebugMentorState): boolean {
  return Boolean(state.stage === "ready" && state.result?.fixed_code && !state.appliedFix);
}

/** 教育提示文案：鼓励先自己改。 */
export function debugMentorGuidance(unlockedLevel: number): string {
  if (unlockedLevel <= 1) {
    return "先按提示自己改一版，运行看看；实在卡住再解锁下一条提示。";
  }
  if (unlockedLevel === 2) {
    return "还有最后一条参考思路。试着自己写出修复，再对照 AI 的版本。";
  }
  return "参考修复已可应用：应用后会自动在服务端沙箱重新编译验证。";
}
