import type {
  AgentEvent,
  AnalysisPlan,
  DebateReport,
  DecisionReport,
  GraphConstraints,
  KnowledgeContextItem,
  PedagogyReport,
  RetrievalTraceItem,
  Resource,
  ResourceType,
  StudentProfile,
  VerificationReport,
  WorkflowPackage
} from "../api/client";

export type MasteryStatus = "not_started" | "severe_weak" | "basic" | "good" | "proficient";

export type StageStatus = "pending" | "running" | "done" | "failed";

export interface CollaborationStage {
  key: string;
  label: string;
  agent: string;
  modelTier?: string;
  status: StageStatus;
  detail: string;
  score?: number;
}

export interface ResourceBranch {
  type: ResourceType;
  label: string;
  status: StageStatus;
  title?: string;
}

export interface ExplainabilityInfo {
  profileDimensions: Array<{ label: string; value: string }>;
  currentNode?: string;
  predecessors: string[];
  successors: string[];
  parent?: string;
  citationCount: number;
}

export interface AgentCollaborationViewModel {
  stages: CollaborationStage[];
  branches: ResourceBranch[];
  explainability: ExplainabilityInfo;
  mastery: MasteryStatus;
  evidenceCount: number;
  decision?: string;
}

export const resourceBranchLabels: Record<ResourceType, string> = {
  document: "讲解文档",
  mind_map: "思维导图",
  exercise: "分层练习",
  code_lab: "代码实操",
  video: "视频脚本",
  reading: "拓展阅读"
};

const allResourceTypes: ResourceType[] = [
  "document",
  "mind_map",
  "exercise",
  "code_lab",
  "video",
  "reading"
];

export function masteryStatusFromScore(score: number): MasteryStatus {
  const normalized = score > 1 ? score / 100 : score;
  if (normalized < 0.6) {
    return "severe_weak";
  }
  if (normalized < 0.75) {
    return "basic";
  }
  if (normalized < 0.9) {
    return "good";
  }
  return "proficient";
}

function isNonEmpty(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  return Boolean(value);
}

function formatScore(value: number | undefined): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function buildBranches(
  resources: Resource[],
  events: AgentEvent[],
  requestedTypes: ResourceType[]
): ResourceBranch[] {
  const resourceByType = new Map<ResourceType, Resource>();
  resources.forEach((resource) => resourceByType.set(resource.type, resource));

  const completedEvents = new Set(
    events
      .filter((event) => event.event === "agent_completed" && event.resource_type)
      .map((event) => event.resource_type)
  );

  const types = requestedTypes.length ? requestedTypes : allResourceTypes;
  return types.map((type) => {
    const resource = resourceByType.get(type);
    const done = Boolean(resource) || completedEvents.has(type);
    return {
      type,
      label: resourceBranchLabels[type],
      status: done ? "done" : "pending",
      title: resource?.title
    };
  });
}

function buildExplainability(
  profile: StudentProfile | undefined,
  graphConstraints: GraphConstraints | undefined,
  resources: Resource[]
): ExplainabilityInfo {
  const profileDimensions = profile
    ? [
        { label: "知识基础", value: profile.knowledge_foundation },
        { label: "学习风格", value: profile.learning_style },
        { label: "认知风格", value: profile.cognitive_style },
        { label: "薄弱点", value: profile.weak_points.join("、") || "暂无" },
        { label: "资源偏好", value: profile.resource_preference.join("、") },
        { label: "时间安排", value: profile.time_preference }
      ].filter((item) => item.value)
    : [];

  const citationCount = resources.reduce(
    (total, resource) => total + (resource.citation_chunk_ids?.length ?? 0),
    0
  );

  return {
    profileDimensions,
    currentNode: graphConstraints?.current_node?.name,
    predecessors: (graphConstraints?.predecessors ?? []).map((node) => node.name),
    successors: (graphConstraints?.successors ?? []).map((node) => node.name),
    parent: graphConstraints?.parent?.name,
    citationCount
  };
}

export function buildAgentCollaboration(
  pkg: WorkflowPackage | undefined,
  running: boolean,
  requestedTypes: ResourceType[] = []
): AgentCollaborationViewModel {
  const resources = pkg?.resources ?? [];
  const events = pkg?.agent_events ?? [];
  const retrievalTrace: RetrievalTraceItem[] = pkg?.retrieval_trace ?? [];
  const knowledgeContext: KnowledgeContextItem[] = pkg?.knowledge_context ?? [];
  const analysisPlan: AnalysisPlan | undefined = pkg?.analysis_plan;
  const verificationReport: VerificationReport | undefined = pkg?.verification_report;
  const pedagogyReport: PedagogyReport | undefined = pkg?.pedagogy_report;
  const debateReport: DebateReport | undefined = pkg?.debate_report;
  const decisionReport: DecisionReport | undefined = pkg?.decision_report;
  const graphConstraints = pkg?.graph_constraints;

  const hasAnalysis = isNonEmpty(analysisPlan);
  const hasRetrieval = retrievalTrace.length > 0 || knowledgeContext.length > 0;
  const hasVerification = isNonEmpty(verificationReport);
  const hasPedagogy = isNonEmpty(pedagogyReport);
  const hasDebate = isNonEmpty(debateReport);
  const hasDecision = isNonEmpty(decisionReport);

  const status = (active: boolean): StageStatus => {
    if (active) {
      return "done";
    }
    return running ? "running" : "pending";
  };

  const stages: CollaborationStage[] = [
    {
      key: "analysis",
      label: "分析规划",
      agent: analysisPlan?.agent || "规划 Agent",
      modelTier: "DeepSeek-V4",
      status: status(hasAnalysis),
      detail: analysisPlan?.topic
        ? `读取画像与图谱约束，规划 ${analysisPlan.topic}`
        : "读取学生画像与知识图谱约束"
    },
    {
      key: "retrieval",
      label: "多路检索",
      agent: "检索 Agent",
      status: status(hasRetrieval),
      detail: hasRetrieval
        ? `命中 ${retrievalTrace.length || knowledgeContext.length} 条证据，含图谱扩展与 MySQL 原文回表`
        : "平台知识库语义检索 + graph-server 扩展"
    },
    {
      key: "generation",
      label: "并行生成 6 类资源",
      agent: "资源生成 Agent 组",
      status: status(resources.length > 0),
      detail: resources.length ? `已生成 ${resources.length} 个资源` : "六个生成分支并行调用"
    },
    {
      key: "fact_check",
      label: "事实校验",
      agent: "事实校验 Agent",
      modelTier: "DeepSeek-V4",
      status: status(hasVerification),
      detail: verificationReport?.hallucination_risk || "核对证据引用与幻觉风险",
      score: formatScore(verificationReport?.fact_score)
    },
    {
      key: "pedagogy",
      label: "教学适配",
      agent: "教学适配 Agent",
      modelTier: "GLM-5",
      status: status(hasPedagogy),
      detail: pedagogyReport?.decision || "检查教学目标与画像对齐",
      score: formatScore(pedagogyReport?.score)
    },
    {
      key: "debate",
      label: "双模型辩论",
      agent: "交叉评审",
      modelTier: "DeepSeek-V4 × GLM-5",
      status: status(hasDebate),
      detail: debateReport?.debate_summary || debateReport?.decision || "两个异源模型交叉评审冲突点"
    },
    {
      key: "decision",
      label: "决策裁决",
      agent: "决策 Agent",
      status: decisionReport?.decision === "rejected" ? "failed" : status(hasDecision),
      detail: decisionReport?.reason || "accepted / retrieve_more / revise 三态路由",
      score: formatScore(decisionReport?.scores?.fact_score)
    }
  ];

  const branches = buildBranches(resources, events, requestedTypes);
  const explainability = buildExplainability(pkg?.profile, graphConstraints, resources);

  const decisionScore = decisionReport?.scores?.fact_score;
  const mastery: MasteryStatus =
    typeof decisionScore === "number"
      ? masteryStatusFromScore(decisionScore)
      : "not_started";

  return {
    stages,
    branches,
    explainability,
    mastery,
    evidenceCount: knowledgeContext.length,
    decision: decisionReport?.decision
  };
}
