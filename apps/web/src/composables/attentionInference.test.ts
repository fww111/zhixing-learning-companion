import {
  AttentionStateMachine,
  AttentionWindowAggregator,
  DEFAULT_ATTENTION_THRESHOLDS,
  extractFaceSignals,
  type FaceFrameSignals
} from "./attentionInference.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

function blendshape(scoreMap: Record<string, number>): { categoryName: string; score: number }[] {
  return Object.entries(scoreMap).map(([categoryName, score]) => ({ categoryName, score }));
}

function frame(overrides: Partial<FaceFrameSignals>): FaceFrameSignals {
  return {
    hasFace: true,
    browFurrow: 0.05,
    squint: 0.05,
    gazeX: 0,
    gazeY: 0,
    yawDeg: 0,
    pitchDeg: 0,
    blinkBoth: 0,
    timestampMs: 0,
    ...overrides
  };
}

function columnMajorIdentityWithYaw(yawRad: number): number[] {
  // 绕 Y 轴旋转矩阵，按 column-major 展开（r[C*4+R]）
  const c = Math.cos(yawRad);
  const s = Math.sin(yawRad);
  // R = [[c,0,s],[0,1,0],[-s,0,c]]
  return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1];
}

test("extractFaceSignals averages blendshapes and derives euler angles", () => {
  const signals = extractFaceSignals(
    blendshape({
      browDownLeft: 0.4,
      browDownRight: 0.6,
      eyeSquintLeft: 0.2,
      eyeSquintRight: 0.4,
      eyeBlinkLeft: 0.8,
      eyeBlinkRight: 0.2,
      eyeLookOutLeft: 0.6,
      eyeLookInRight: 0.6,
      eyeLookInLeft: 0.05,
      eyeLookOutRight: 0.05
    }),
    columnMajorIdentityWithYaw(Math.PI / 6),
    1000
  );

  assert(Math.abs(signals.browFurrow - 0.425) < 1e-6, "browFurrow should weight browDown* mean by 0.85");
  assert(Math.abs(signals.squint - 0.3) < 1e-6, "squint should be mean of eyeSquint*");
  assert(Math.abs(signals.blinkBoth - 0.5) < 1e-6, "blinkBoth should average both eyes");
  assert(signals.gazeX < -0.35, "both eyes looking left should give negative gazeX");
  assert(Math.abs(signals.yawDeg - 30) < 1e-6, "yaw should be ~30 degrees for PI/6 rotation");
  assert(signals.hasFace, "non-empty blendshapes mean a face is present");
});

test("extractFaceSignals handles empty input", () => {
  const signals = extractFaceSignals([], undefined, 0);
  assert(!signals.hasFace, "empty blendshapes means no face");
  assert(signals.browFurrow === 0 && signals.gazeX === 0, "signals default to zero");
});

test("sustained brow furrow switches to confused after confirm window", () => {
  const machine = new AttentionStateMachine({ ...DEFAULT_ATTENTION_THRESHOLDS, confusedConfirmMs: 2000 });
  const start = 10_000;

  // 前 1.5 秒专注（超过 focusedConfirmMs，先让状态机从 no_face 进入 focused）
  let ts = start;
  for (; ts < start + 1500; ts += 100) {
    machine.update(frame({ timestampMs: ts }));
  }
  // 皱眉 1 秒：尚未达到 2s 确认窗口，应保持 focused
  for (; ts < start + 2500; ts += 100) {
    const snapshot = machine.update(frame({ browFurrow: 0.5, timestampMs: ts }));
    assert(snapshot.state === "focused", `short furrow should stay focused, got ${snapshot.state}`);
  }
  // 皱眉满 2 秒：切换 confused
  const confirmed = machine.update(frame({ browFurrow: 0.5, timestampMs: start + 3600 }));
  assert(confirmed.state === "confused", `sustained furrow should become confused, got ${confirmed.state}`);
  assert(confirmed.confidence >= 0.55, "confidence should be in reasonable range");
});

test("transient confusion within confirm window does not flip state", () => {
  const machine = new AttentionStateMachine({ ...DEFAULT_ATTENTION_THRESHOLDS, confusedConfirmMs: 2000 });
  const start = 10_000;
  let ts = start;
  for (; ts < start + 1500; ts += 100) {
    machine.update(frame({ timestampMs: ts }));
  }
  for (; ts < start + 2400; ts += 100) {
    machine.update(frame({ browFurrow: 0.6, timestampMs: ts }));
  }
  // 未满确认窗口就恢复专注
  const recovered = machine.update(frame({ timestampMs: ts }));
  assert(recovered.state === "focused", `transient furrow must not flip state, got ${recovered.state}`);
});

test("sustained side gaze becomes distracted", () => {
  const machine = new AttentionStateMachine({ ...DEFAULT_ATTENTION_THRESHOLDS, distractedConfirmMs: 1500 });
  const start = 10_000;
  let ts = start;
  for (; ts < start + 1500; ts += 100) {
    machine.update(frame({ timestampMs: ts }));
  }
  for (; ts < start + 3000; ts += 100) {
    machine.update(frame({ gazeX: 0.8, timestampMs: ts }));
  }
  const snapshot = machine.update(frame({ gazeX: 0.8, timestampMs: start + 3100 }));
  assert(snapshot.state === "distracted", `side gaze should be distracted, got ${snapshot.state}`);
});

test("large yaw also counts as distracted", () => {
  const machine = new AttentionStateMachine({ ...DEFAULT_ATTENTION_THRESHOLDS, distractedConfirmMs: 1000 });
  const start = 10_000;
  let ts = start;
  for (; ts < start + 1500; ts += 100) {
    machine.update(frame({ yawDeg: 45, timestampMs: ts }));
  }
  const snapshot = machine.update(frame({ yawDeg: 45, timestampMs: start + 1600 }));
  assert(snapshot.state === "distracted", `large yaw should be distracted, got ${snapshot.state}`);
});

test("long eye closure triggers tired", () => {
  const machine = new AttentionStateMachine({ ...DEFAULT_ATTENTION_THRESHOLDS, tiredConfirmMs: 1200 });
  const start = 10_000;
  let ts = start;
  for (; ts < start + 1500; ts += 100) {
    machine.update(frame({ timestampMs: ts }));
  }
  // 长闭眼 700ms
  for (; ts < start + 2200; ts += 100) {
    machine.update(frame({ blinkBoth: 0.9, timestampMs: ts }));
  }
  // 睁眼后长闭眼被记录（longBlinkSeen），tired 候选需持续 1200ms 才确认
  let snapshot = machine.update(frame({ timestampMs: ts }));
  for (; ts < start + 3950; ts += 100) {
    snapshot = machine.update(frame({ timestampMs: ts }));
  }
  assert(snapshot.state === "tired", `long blink should become tired, got ${snapshot.state}`);
});

test("missing face for a while becomes no_face", () => {
  const machine = new AttentionStateMachine({ ...DEFAULT_ATTENTION_THRESHOLDS, noFaceConfirmMs: 1500 });
  const start = 10_000;
  let ts = start;
  for (; ts < start + 1600; ts += 100) {
    machine.update(frame({ hasFace: false, timestampMs: ts }));
  }
  const snapshot = machine.update(frame({ hasFace: false, timestampMs: start + 1700 }));
  assert(snapshot.state === "no_face", `lost face should become no_face, got ${snapshot.state}`);
});

test("aggregator computes time-weighted distribution over sliding window", () => {
  const aggregator = new AttentionWindowAggregator();
  // 0-30s focused，30-50s confused，50-70s focused → 最近 60s（10-70s）：
  // focused = 20+20=40s，confused = 20s
  aggregator.push("focused", 0);
  aggregator.push("confused", 30_000);
  aggregator.push("focused", 50_000);
  aggregator.push("focused", 70_000);

  const distribution = aggregator.distribution(60_000, 70_000);
  assert(distribution.confused === 0.33 || distribution.confused === 0.34,
    `confused should be ~1/3, got ${distribution.confused}`);
  assert(distribution.focused + distribution.confused <= 1.01, "distribution should sum to ~1");
  const dominant = aggregator.dominant(60_000, 70_000);
  assert(dominant === "focused", "dominant should be focused");
});

test("aggregator falls back to focused for uncovered startup time", () => {
  const aggregator = new AttentionWindowAggregator();
  aggregator.push("confused", 55_000);
  aggregator.push("confused", 60_000);
  const distribution = aggregator.distribution(60_000, 60_000);
  assert(distribution.confused === 0.08, `5s of 60s should be 0.08, got ${distribution.confused}`);
  assert(distribution.focused === 0.92, `uncovered time should be focused, got ${distribution.focused}`);
});

console.log("attentionInference tests passed");
