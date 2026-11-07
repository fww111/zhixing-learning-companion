import {
  decideIntervention,
  DEFAULT_ATTENTION_THRESHOLDS,
  interventionCopy,
  loadAttentionThresholds,
  recentCodeFailures,
  saveAttentionThresholds,
  type AttentionThresholds,
  type CodeFailureRecord
} from "./attentionInterventionModel.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual<T>(actual: T, expected: T, label: string) {
  const same = Object.is(actual, expected)
    || (typeof actual === "object" && typeof expected === "object" && JSON.stringify(actual) === JSON.stringify(expected));
  if (!same) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)} but got ${JSON.stringify(actual)}`);
  }
}

function failure(at: number, summary = "compile_error"): CodeFailureRecord {
  return { at, summary };
}

function testDefaults() {
  assertEqual(DEFAULT_ATTENTION_THRESHOLDS.confusedMs, 15_000, "confused default 15s");
  assertEqual(DEFAULT_ATTENTION_THRESHOLDS.distractedMs, 20_000, "distracted default 20s");
  assertEqual(DEFAULT_ATTENTION_THRESHOLDS.maxPerNode, 2, "max per node 2");
}

function testStandardInterventionAt15s() {
  const decision = decideIntervention({
    state: "confused",
    heldMs: 15_000,
    nodeCount: 0,
    codeFailures: [],
    now: 1_000_000
  });
  assertEqual(decision.kind, "standard", "confused 15s triggers standard");
  assert(decision.reason.includes("15 秒"), "reason mentions seconds");
  assert(!decision.lastError, "no code error on standard path");

  const tooEarly = decideIntervention({
    state: "confused",
    heldMs: 14_000,
    nodeCount: 0,
    codeFailures: [],
    now: 1_000_000
  });
  assertEqual(tooEarly.kind, "none", "confused under threshold stays quiet");
}

function testMaxPerNodeGuard() {
  const decision = decideIntervention({
    state: "confused",
    heldMs: 20_000,
    nodeCount: 2,
    codeFailures: [],
    now: 1_000_000
  });
  assertEqual(decision.kind, "none", "max per node blocks standard");
}

function testHighConfidenceCodeFailures() {
  const now = 1_000_000;
  const decision = decideIntervention({
    state: "confused",
    heldMs: 4_500, // 未到 15s，但双信号命中
    nodeCount: 0,
    codeFailures: [failure(now - 60_000), failure(now - 20_000)],
    now
  });
  assertEqual(decision.kind, "high_confidence", "code failures x confused fires early");
  assertEqual(decision.lastError, "compile_error", "last error surfaced");

  const singleFailure = decideIntervention({
    state: "confused",
    heldMs: 4_500,
    nodeCount: 0,
    codeFailures: [failure(now - 30_000)],
    now
  });
  assertEqual(singleFailure.kind, "none", "one failure is not enough");

  const notConfused = decideIntervention({
    state: "focused",
    heldMs: 60_000,
    nodeCount: 0,
    codeFailures: [failure(now - 10_000), failure(now - 5_000)],
    now
  });
  assertEqual(notConfused.kind, "none", "failures without confused stay quiet");
}

function testCodeFailureWindowFilters() {
  const now = 1_000_000;
  const windowMs = DEFAULT_ATTENTION_THRESHOLDS.codeFailureWindowMs;
  const failures = [
    failure(now - windowMs - 1_000), // 窗口外
    failure(now - 40_000),
    failure(now - 10_000)
  ];
  assertEqual(recentCodeFailures(failures, now, windowMs).length, 2, "stale failure excluded");

  const decision = decideIntervention({
    state: "confused",
    heldMs: 4_500,
    nodeCount: 0,
    codeFailures: failures,
    now
  });
  assertEqual(decision.kind, "high_confidence", "two in-window failures still fire");
}

function testDistractedGentleReminder() {
  const now = 1_000_000;
  const decision = decideIntervention({
    state: "distracted",
    heldMs: 20_000,
    nodeCount: 0,
    codeFailures: [],
    now
  });
  assertEqual(decision.kind, "gentle", "distracted 20s fires gentle");

  const cooldown = decideIntervention({
    state: "distracted",
    heldMs: 30_000,
    nodeCount: 0,
    codeFailures: [],
    now,
    lastGentleAt: now - 60_000
  });
  assertEqual(cooldown.kind, "none", "gentle respects cooldown");
}

function testThresholdOverrides() {
  const custom: AttentionThresholds = { ...DEFAULT_ATTENTION_THRESHOLDS, confusedMs: 5_000 };
  const decision = decideIntervention({
    thresholds: custom,
    state: "confused",
    heldMs: 6_000,
    nodeCount: 0,
    codeFailures: [],
    now: 1_000_000
  });
  assertEqual(decision.kind, "standard", "custom 5s threshold fires at 6s");
}

function testCopyVariants() {
  const standard = interventionCopy("standard", "背包问题");
  assert(standard.title.includes("难"), "standard copy mentions difficulty");
  const high = interventionCopy("high_confidence", "背包问题", "undefined reference");
  assert(high.title.includes("代码"), "high confidence copy mentions code");
  assert(high.body.includes("undefined reference"), "high confidence body includes error");
  const gentle = interventionCopy("gentle", "背包问题");
  assert(!gentle.title.includes("AI"), "gentle copy does not push AI");
}

function testPersistThresholds() {
  const store = new Map<string, string>();
  const fakeStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value)
  };
  const saved = saveAttentionThresholds({ confusedMs: 8_000 }, fakeStorage as unknown as Storage);
  assertEqual(saved.confusedMs, 8_000, "saved override applied");
  const loaded = loadAttentionThresholds(fakeStorage as unknown as Storage);
  assertEqual(loaded.confusedMs, 8_000, "loaded override persists");
  assertEqual(loaded.distractedMs, DEFAULT_ATTENTION_THRESHOLDS.distractedMs, "other fields keep defaults");

  // 非法值回退默认
  store.set("pla_attention_thresholds", JSON.stringify({ confusedMs: -5 }));
  const safe = loadAttentionThresholds(fakeStorage as unknown as Storage);
  assertEqual(safe.confusedMs, DEFAULT_ATTENTION_THRESHOLDS.confusedMs, "invalid value falls back");
}

const tests = [
  testDefaults,
  testStandardInterventionAt15s,
  testMaxPerNodeGuard,
  testHighConfidenceCodeFailures,
  testCodeFailureWindowFilters,
  testDistractedGentleReminder,
  testThresholdOverrides,
  testCopyVariants,
  testPersistThresholds
];
for (const test of tests) {
  test();
}
console.log(`attentionInterventionModel: ${tests.length} tests passed`);
