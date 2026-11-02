import {
  buildAgentCollaboration,
  masteryStatusFromScore
} from "./agentCollaborationModel.js";
import type { WorkflowPackage } from "../api/client";

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

const profile = {
  student_id: "s1",
  major: "软件工程",
  grade: "大三",
  learning_goal: "掌握 C++",
  knowledge_foundation: "有 C 基础",
  learning_style: "视觉型",
  cognitive_style: "归纳型",
  weak_points: ["指针"],
  time_preference: "周末",
  resource_preference: ["图解"],
  motivation: "强",
  constraints: [],
  assessment_preference: "笔试",
  knowledge_graph_focus: [],
  confidence_score: 0.8,
  completion_score: 0.7,
  updated_evidence: []
};

const fullPackage = {
  event: "completed",
  profile,
  resources: [
    {
      id: "r1",
      type: "document",
      title: "指针讲解",
      topic: "指针",
      content: "c",
      recommendation_reason: "契合薄弱点",
      tags: [],
      citation_chunk_ids: [1, 2]
    }
  ],
  learning_path: { student_id: "s1", stages: [] },
  analysis_plan: { agent: "规划 Agent", topic: "指针" },
  retrieval_trace: [{ query: "指针" }],
  knowledge_context: [{ source_locator: "doc#1", content: "x" }],
  verification_report: { decision: "ok", evidence_count: 1, fact_score: 0.9 },
  pedagogy_report: { agent: "p", score: 0.85, decision: "ok" },
  debate_report: { agent: "d", debate_summary: "分歧已解决", decision: "ok" },
  decision_report: {
    agent: "dec",
    decision: "accepted",
    next_action: "deliver",
    revision_count: 1,
    max_revision_count: 2,
    reason: "通过",
    fallback_available: false,
    scores: { fact_score: 0.92 }
  },
  graph_constraints: {
    current_node: { id: "n1", name: "指针" },
    predecessors: [{ id: "p", name: "变量" }],
    successors: [{ id: "s", name: "引用" }]
  },
  agent_events: [{ event: "agent_completed", agent: "doc", summary: "done" }]
} as unknown as WorkflowPackage;

test("empty package leaves every stage pending", () => {
  const model = buildAgentCollaboration(undefined, false);
  assert(
    model.stages.every((stage) => stage.status === "pending"),
    "all stages should be pending without data"
  );
  assert(model.mastery === "not_started", "default mastery is not_started");
});

test("full package marks pipeline done and maps explainability", () => {
  const model = buildAgentCollaboration(fullPackage, false);
  assert(
    model.stages.every((stage) => stage.status === "done"),
    "all stages should be done with complete package"
  );
  assert(model.decision === "accepted", "decision should be accepted");
  assert(
    model.explainability.predecessors[0] === "变量",
    "predecessor name should be mapped"
  );
  assert(
    model.explainability.successors[0] === "引用",
    "successor name should be mapped"
  );
  assert(
    model.explainability.citationCount === 2,
    "citation count should be summed"
  );
  assert(
    model.explainability.profileDimensions.length >= 5,
    "profile dimensions should be present"
  );
  assert(model.mastery === "proficient", "0.92 score maps to proficient");
});

test("mastery score thresholds", () => {
  assert(masteryStatusFromScore(0.4) === "severe_weak", "0.4 severe_weak");
  assert(masteryStatusFromScore(0.7) === "basic", "0.7 basic");
  assert(masteryStatusFromScore(0.8) === "good", "0.8 good");
  assert(masteryStatusFromScore(0.95) === "proficient", "0.95 proficient");
  assert(masteryStatusFromScore(80) === "good", "80/100 normalized to good");
});
