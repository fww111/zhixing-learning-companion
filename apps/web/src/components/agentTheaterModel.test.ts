import {
  buildTheaterGraph,
  buildTheaterTraceCard,
  theaterNodeClassName,
  theaterStatusText,
  THEATER_HEIGHT,
  THEATER_WIDTH
} from "./agentTheaterModel.js";
import { buildAgentCollaboration } from "./agentCollaborationModel.js";
import type { WorkflowPackage } from "../api/client.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

const completedPkg = {
  agent_events: [],
  analysis_plan: { agent: "规划 Agent", topic: "指针与数组" },
  retrieval_trace: [{ query: "指针" }],
  knowledge_context: [{ chunk_id: 1, source_locator: "p3", content: "教材", heading: "指针", retrieval_query: "指针", storage: "mysql" }],
  graph_constraints: {
    current_node: { id: "n1", name: "指针入门" },
    predecessors: [],
    successors: [],
    related: []
  },
  verification_report: { decision: "accepted", fact_score: 0.92 },
  pedagogy_report: { decision: "aligned", score: 0.88 },
  debate_report: { decision: "accepted", debate_summary: "双模型一致" },
  decision_report: { decision: "accepted", reason: "证据充分", scores: { fact_score: 0.92 } },
  resources: [
    { type: "document", title: "指针讲解" },
    { type: "mind_map", title: "指针导图" }
  ],
  profile: undefined
} as unknown as WorkflowPackage;

function testTheaterGraphShape() {
  const vm = buildAgentCollaboration(completedPkg, false, ["document", "mind_map"]);
  const graph = buildTheaterGraph(vm);

  const mainNodes = graph.nodes.filter((node) => !node.isBranch);
  assert(mainNodes.length === 7, "seven main stations");
  assert(graph.nodes.some((node) => node.key === "branch-document"), "document branch node");
  assert(graph.nodes.some((node) => node.key === "branch-mind_map"), "mind map branch node");
  assert(graph.links.some((link) => link.kind === "main" && link.to === "decision"), "main chain reaches decision");
  assert(graph.links.every((link) => link.from !== link.to), "no self links");
  assert(graph.nodes.every((node) => node.x >= 0 && node.x <= THEATER_WIDTH && node.y >= 0 && node.y <= THEATER_HEIGHT), "nodes inside stage bounds");

  const decision = mainNodes.find((node) => node.key === "decision");
  assert(decision?.status === "done", "decision done when reports exist");
  const debate = mainNodes.find((node) => node.key === "debate");
  assert(debate?.dualModel === true, "debate marked dual model");
}

function testPendingState() {
  const vm = buildAgentCollaboration(undefined, true);
  const graph = buildTheaterGraph(vm);
  const generation = graph.nodes.find((node) => node.key === "generation");
  assert(generation?.status === "running", "generation runs while pending");
  const allPendingOrRunning = graph.nodes.every((node) => node.status === "pending" || node.status === "running");
  assert(allPendingOrRunning, "no node done on empty package");
}

function testClassNamesAndStatus() {
  const vm = buildAgentCollaboration(completedPkg, false);
  const graph = buildTheaterGraph(vm);
  const decision = graph.nodes.find((node) => node.key === "decision")!;
  assert(theaterNodeClassName(decision).includes("is-done"), "done class");
  assert(theaterStatusText(decision) === "92分", "decision shows score");
  const pendingNode = graph.nodes.find((node) => node.status === "pending");
  if (pendingNode) {
    assert(theaterStatusText(pendingNode) === "待启动", "pending text");
  }
}

function testTraceCard() {
  const vm = buildAgentCollaboration(completedPkg, false, ["document", "mind_map"]);
  const trace = buildTheaterTraceCard(vm, "generation");
  assert(trace.stage?.key === "generation", "generation stage");
  assert(trace.branches.length === 2, "branches listed for generation node");
  assert(trace.decision === "accepted", "decision surfaced");
  const other = buildTheaterTraceCard(vm, "debate");
  assert(other.stage?.label === "双模型辩论", "debate trace stage");
  assert(other.branches.length === 0, "no branches on debate node");
}

const tests = [testTheaterGraphShape, testPendingState, testClassNamesAndStatus, testTraceCard];
for (const test of tests) {
  test();
}
console.log(`agentTheaterModel: ${tests.length} tests passed`);
