import type { DebugHintResult } from "../api/client.js";
import {
  applyAIFix,
  canApplyFix,
  debugCategoryLabel,
  debugMentorFailed,
  debugMentorGuidance,
  debugMentorLoading,
  debugMentorReady,
  initialDebugMentorState,
  unlockNextHint,
  type DebugMentorState
} from "./debugMentorModel.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

const sample: DebugHintResult = {
  diagnosis: "循环边界写到了 size。",
  error_category: "boundary",
  hints: ["检查下标范围", "用 i < size", "改为 i < 3"],
  fixed_code: "for (int i = 0; i < 3; i++) {}",
  key_concept: "数组边界",
  evidence_chunks: [],
  verification: { decision: "accepted" }
};

function testStageFlow() {
  let state: DebugMentorState = initialDebugMentorState();
  assert(state.stage === "idle" && state.unlockedLevel === 0, "initial state");

  state = debugMentorLoading(state);
  assert(state.stage === "loading", "loading");

  state = debugMentorReady(state, sample);
  assert(state.stage === "ready", "ready");
  assert(state.unlockedLevel === 1, "first hint unlocked on ready");

  state = unlockNextHint(state);
  assert(state.unlockedLevel === 2, "second hint");

  state = unlockNextHint(state);
  assert(state.unlockedLevel === 3, "third hint");

  state = unlockNextHint(state);
  assert(state.unlockedLevel === 3, "capped at 3");
}

function testApplyFix() {
  let state: DebugMentorState = debugMentorReady(initialDebugMentorState(), sample);
  assert(canApplyFix(state), "fix available before apply");

  const { state: next, fixedCode } = applyAIFix(state);
  assert(fixedCode === sample.fixed_code, "fixed code returned");
  assert(next.appliedFix === sample.fixed_code, "applied recorded");
  assert(!canApplyFix(next), "fix button hidden after apply");
}

function testNoFixCode() {
  const noFix: DebugHintResult = { ...sample, fixed_code: "" };
  const state = debugMentorReady(initialDebugMentorState(), noFix);
  assert(!canApplyFix(state), "no apply button without fixed_code");
}

function testErrorAndGuidance() {
  let state = debugMentorFailed(initialDebugMentorState(), "网络错误");
  assert(state.stage === "error" && state.error === "网络错误", "error state");

  assert(debugMentorGuidance(1).includes("自己改"), "guidance level 1");
  assert(debugMentorGuidance(2).includes("最后一条"), "guidance level 2");
  assert(debugMentorGuidance(3).includes("沙箱"), "guidance level 3");
}

function testCategoryLabel() {
  assert(debugCategoryLabel("syntax") === "语法错误", "syntax label");
  assert(debugCategoryLabel("boundary") === "越界/非法访问", "boundary label");
  assert(debugCategoryLabel("output") === "输出不一致", "output label");
}

const tests = [testStageFlow, testApplyFix, testNoFixCode, testErrorAndGuidance, testCategoryLabel];
for (const test of tests) {
  test();
}
console.log(`debugMentorModel: ${tests.length} tests passed`);
