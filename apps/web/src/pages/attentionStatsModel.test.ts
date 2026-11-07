import type { LearningProfileEvent } from "../api/client.js";
import { ATTENTION_STATE_LABELS, buildAttentionStats } from "./attentionStatsModel.js";

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

function sampleEvent(overrides: Partial<LearningProfileEvent> & { dominant?: string }): LearningProfileEvent {
  const { dominant, ...rest } = overrides;
  return {
    id: 1,
    user_id: 1,
    course_id: 1,
    student_profile_id: 1,
    knowledge_node_id: "n1",
    lesson_session_id: null,
    event_type: "attention_sample",
    topic: "背包问题",
    detail: "",
    event_payload: { dominant: dominant ?? "focused" },
    evidence_strength: "weak",
    score: null,
    created_at: "2026-11-07T10:00:00",
    ...rest
  };
}

function testAggregation() {
  const events = [
    sampleEvent({ id: 1, dominant: "focused", created_at: "2026-11-07T10:00:00" }),
    sampleEvent({ id: 2, dominant: "focused", created_at: "2026-11-07T10:00:10" }),
    sampleEvent({ id: 3, dominant: "confused", created_at: "2026-11-07T10:00:20" }),
    sampleEvent({ id: 4, dominant: "distracted", created_at: "2026-11-07T10:00:30" }),
    sampleEvent({ id: 5, dominant: "tired", created_at: "2026-11-07T10:00:40" }),
    // 非采样事件应被忽略
    sampleEvent({ id: 6, event_type: "lesson_viewed", dominant: "focused" }),
    // 非法 dominant 应被忽略
    sampleEvent({ id: 7, dominant: "hacking", created_at: "2026-11-07T10:00:50" }),
    sampleEvent({ id: 8, dominant: "focused", created_at: "2026-11-07T10:01:00" })
  ];
  const stats = buildAttentionStats(events);
  assertEqual(stats.total, 6, "valid samples counted");
  assertEqual(stats.focused, 3, "focused count");
  assertEqual(stats.confused, 1, "confused count");
  assertEqual(stats.distracted, 1, "distracted count");
  assertEqual(stats.tired, 1, "tired count");
  assertEqual(stats.noFace, 0, "no_face count");
  assertEqual(stats.focusedPercent, 50, "focused percent");
  assertEqual(stats.confusedPercent, 17, "confused percent");
  assertEqual(stats.lastSampleAt, "2026-11-07T10:01:00", "last sample time");
  assertEqual(stats.topics, ["背包问题"], "topics collected");
  assertEqual(stats.confusedSignal, false, "no signal under threshold");
}

function testConfusedSignal() {
  const events = [
    sampleEvent({ id: 1, dominant: "confused" }),
    sampleEvent({ id: 2, dominant: "confused" }),
    sampleEvent({ id: 3, dominant: "confused" }),
    sampleEvent({ id: 4, dominant: "focused" }),
    sampleEvent({ id: 5, dominant: "focused" }),
    sampleEvent({ id: 6, dominant: "focused" })
  ];
  const stats = buildAttentionStats(events);
  assertEqual(stats.confusedPercent, 50, "confused percent high");
  assertEqual(stats.confusedSignal, true, "confused signal fires at >=30% with >=5 samples");
}

function testEmpty() {
  const stats = buildAttentionStats([]);
  assertEqual(stats.total, 0, "empty total");
  assertEqual(stats.focusedPercent, null, "empty focused percent is null");
  assertEqual(stats.confusedPercent, null, "empty confused percent is null");
  assertEqual(stats.confusedSignal, false, "empty has no signal");
  assertEqual(stats.lastSampleAt, "", "empty last sample");
  assertEqual(stats.topics, [], "empty topics");
}

function testLabels() {
  assertEqual(ATTENTION_STATE_LABELS.focused, "专注", "focused label");
  assertEqual(ATTENTION_STATE_LABELS.no_face, "离席", "no_face label");
}

const tests = [testAggregation, testConfusedSignal, testEmpty, testLabels];
for (const test of tests) {
  test();
}
console.log(`attentionStatsModel: ${tests.length} tests passed`);
