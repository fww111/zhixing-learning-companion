import { buildLessonProfileEvent } from "./learningProfileEventModel.js";

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

test("lesson resource actions map to course-scoped profile events", () => {
  const event = buildLessonProfileEvent({
    action: "mind_map_interacted",
    topic: "function call flow",
    nodeId: "py-function-call",
    payload: { expanded_branches: 5 }
  });
  const payload = event.event_payload || {};

  assert(event.event_type === "mind_map_interacted", "mind map action should keep event type");
  assert(event.knowledge_node_id === "py-function-call", "node id should be preserved");
  assert(payload.resource_type === "mind_map", "resource type should be mind_map");
  assert(payload.expanded_branches === 5, "payload should preserve interaction evidence");
  assert(event.evidence_strength === "medium", "mind map evidence should be medium strength");
});

test("passed code runs become strong profile evidence", () => {
  const event = buildLessonProfileEvent({
    action: "code_attempt_passed",
    topic: "loop boundary control",
    nodeId: "py-loop-boundary",
    score: 1,
    payload: { attempts: 2, passed: true }
  });
  const payload = event.event_payload || {};

  assert(event.event_type === "code_attempt_passed", "passed code should use passed event");
  assert(payload.resource_type === "code_lab", "code events should be code_lab resources");
  assert(event.evidence_strength === "strong", "passed code should be strong evidence");
  assert(event.score === 1, "score should be preserved");
});

test("classroom completion records OpenMAIC classroom evidence", () => {
  const event = buildLessonProfileEvent({
    action: "classroom_completed",
    topic: "Python basics",
    nodeId: "py-basics",
    payload: { classroom_id: "demo-classroom" }
  });
  const payload = event.event_payload || {};

  assert(event.event_type === "openmaic_classroom_viewed", "classroom completion should record classroom event");
  assert(payload.resource_type === "openmaic_classroom", "resource should identify OpenMAIC");
  assert(event.evidence_strength === "medium", "classroom completion should be medium evidence");
});
