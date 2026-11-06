import type { AgentCollaborationViewModel, CollaborationStage, StageStatus } from "./agentCollaborationModel";

/** 剧场舞台节点：主链 7 站 + 并行生成分支 6 条。 */
export interface TheaterNode {
  key: string;
  label: string;
  agent: string;
  x: number;
  y: number;
  radius: number;
  status: StageStatus;
  score?: number;
  isBranch?: boolean;
  branchLabel?: string;
  dualModel?: boolean;
}

export interface TheaterLink {
  from: string;
  to: string;
  kind: "main" | "branch";
}

export const THEATER_WIDTH = 860;
export const THEATER_HEIGHT = 320;

const MAIN_STATIONS: Array<{ key: string; label: string; x: number; y: number; radius: number; dualModel?: boolean }> = [
  { key: "analysis", label: "分析规划", x: 70, y: 210, radius: 34 },
  { key: "retrieval", label: "多路检索", x: 195, y: 210, radius: 34 },
  { key: "generation", label: "并行生成", x: 330, y: 210, radius: 40 },
  { key: "fact_check", label: "事实校验", x: 465, y: 210, radius: 34 },
  { key: "pedagogy", label: "教学适配", x: 590, y: 210, radius: 34 },
  { key: "debate", label: "双模型辩论", x: 715, y: 210, radius: 40, dualModel: true },
  { key: "decision", label: "决策裁决", x: 835, y: 210, radius: 36 }
];

const BRANCH_KEYS = ["document", "mind_map", "exercise", "code_lab", "video", "reading"] as const;

const BRANCH_POSITIONS: Array<{ x: number; y: number }> = [
  { x: 240, y: 70 },
  { x: 285, y: 42 },
  { x: 335, y: 28 },
  { x: 385, y: 42 },
  { x: 430, y: 70 },
  { x: 455, y: 108 }
];

export function buildTheaterGraph(vm: AgentCollaborationViewModel): { nodes: TheaterNode[]; links: TheaterLink[] } {
  const stageByKey = new Map<string, CollaborationStage>(vm.stages.map((stage) => [stage.key, stage]));
  const nodes: TheaterNode[] = [];
  const links: TheaterLink[] = [];

  for (const station of MAIN_STATIONS) {
    const stage = stageByKey.get(station.key);
    nodes.push({
      key: station.key,
      label: station.label,
      agent: stage?.agent || station.label,
      x: station.x,
      y: station.y,
      radius: station.radius,
      status: stage?.status || "pending",
      score: stage?.score,
      dualModel: station.dualModel
    });
  }
  for (let index = 0; index < MAIN_STATIONS.length - 1; index += 1) {
    links.push({ from: MAIN_STATIONS[index]!.key, to: MAIN_STATIONS[index + 1]!.key, kind: "main" });
  }

  const generation = nodes.find((node) => node.key === "generation");
  const generationDone = generation?.status === "done";
  vm.branches.forEach((branch, index) => {
    const position = BRANCH_POSITIONS[index];
    if (!position) {
      return;
    }
    nodes.push({
      key: `branch-${branch.type}`,
      label: branch.label,
      agent: branch.label,
      x: position.x,
      y: position.y,
      radius: 18,
      status: branch.status === "done" || generationDone ? (branch.status === "done" ? "done" : generation ? generation.status : "pending") : branch.status,
      isBranch: true,
      branchLabel: branch.title
    });
    links.push({ from: `branch-${branch.type}`, to: "generation", kind: "branch" });
  });

  return { nodes, links };
}

export function theaterNodeClassName(node: TheaterNode): string {
  const base = node.isBranch ? "theater-branch" : "theater-node";
  const status = `is-${node.status}`;
  return `${base} ${status}${node.dualModel ? " dual-model" : ""}`;
}

export function theaterStatusText(node: TheaterNode): string {
  if (node.status === "done") {
    return node.score !== undefined ? `${Math.round(node.score * 100)}分` : "完成";
  }
  if (node.status === "running") {
    return "运行中";
  }
  if (node.status === "failed") {
    return "驳回";
  }
  return "待启动";
}

export interface TheaterTraceCard {
  stage: CollaborationStage | undefined;
  branches: Array<{ label: string; status: StageStatus; title?: string }>;
  citationCount: number;
  decision?: string;
}

export function buildTheaterTraceCard(vm: AgentCollaborationViewModel, nodeKey: string): TheaterTraceCard {
  const stage = vm.stages.find((candidate) => candidate.key === nodeKey);
  return {
    stage,
    branches: nodeKey === "generation" ? vm.branches.map((branch) => ({ label: branch.label, status: branch.status, title: branch.title })) : [],
    citationCount: vm.evidenceCount,
    decision: vm.decision
  };
}
