import type { PracticeStep } from "../api/client.js";
import {
  advanceFrame,
  initialVisualizationState,
  stepFrame,
  togglePlay,
  type VisualizationState
} from "./PracticePanel.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

const steps: PracticeStep[] = [
  { array: [5, 2], highlight: [0, 1], label: "比较" },
  { array: [2, 5], highlight: [0, 1], label: "交换" },
  { array: [2, 5], highlight: [], label: "完成" }
];

function testFlow() {
  let state: VisualizationState = initialVisualizationState(steps);
  assert(state.frameIndex === 0 && !state.playing, "initial first frame");

  state = stepFrame(state, steps, "next");
  assert(state.frameIndex === 1 && !state.playing, "step next");

  state = stepFrame(state, steps, "next");
  state = stepFrame(state, steps, "next");
  assert(state.frameIndex === 2, "clamped at last");

  state = stepFrame(state, steps, "next");
  assert(state.frameIndex === 2, "no overflow");

  state = stepFrame(state, steps, "prev");
  assert(state.frameIndex === 1, "step prev");
}

function testPlay() {
  let state: VisualizationState = initialVisualizationState(steps);
  state = togglePlay(state, steps);
  assert(state.playing && state.frameIndex === 0, "play from start");

  state = advanceFrame(state, steps);
  assert(state.frameIndex === 1 && state.playing, "advance while playing");

  state = advanceFrame(state, steps);
  state = advanceFrame(state, steps);
  assert(state.frameIndex === 2 && !state.playing, "stops at last frame");

  state = togglePlay(state, steps);
  assert(state.frameIndex === 0 && state.playing, "replay from start");
}

function testEmptySteps() {
  const state = initialVisualizationState([]);
  assert(state.frameIndex === -1, "no frames");
  assert(stepFrame(state, [], "next").frameIndex === -1, "step no-op on empty");
  assert(!togglePlay(state, []).playing, "play no-op on empty");
}

const tests = [testFlow, testPlay, testEmptySteps];
for (const test of tests) {
  test();
}
console.log(`practiceVisualizerModel: ${tests.length} tests passed`);
