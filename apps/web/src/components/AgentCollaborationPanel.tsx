import {
  CheckCircle2,
  CircleDashed,
  Cpu,
  GitBranch,
  Loader2,
  Network,
  Sparkles,
  XCircle
} from "lucide-react";
import type { ResourceType, WorkflowPackage } from "../api/client";
import {
  buildAgentCollaboration,
  resourceBranchLabels,
  type MasteryStatus,
  type StageStatus
} from "./agentCollaborationModel";

interface AgentCollaborationPanelProps {
  pkg?: WorkflowPackage;
  running: boolean;
  requestedTypes?: ResourceType[];
}

const masteryLabels: Record<MasteryStatus, string> = {
  not_started: "未学习",
  severe_weak: "严重弱项",
  basic: "掌握基础",
  good: "达标良好",
  proficient: "精通"
};

function StageIcon({ status }: { status: StageStatus }) {
  if (status === "done") {
    return <CheckCircle2 size={16} className="acp-icon done" />;
  }
  if (status === "running") {
    return <Loader2 size={16} className="acp-icon running spin" />;
  }
  if (status === "failed") {
    return <XCircle size={16} className="acp-icon failed" />;
  }
  return <CircleDashed size={16} className="acp-icon pending" />;
}

export function AgentCollaborationPanel({
  pkg,
  running,
  requestedTypes = []
}: AgentCollaborationPanelProps) {
  const model = buildAgentCollaboration(pkg, running, requestedTypes);

  return (
    <section className="panel agent-collaboration-panel">
      <div className="panel-title">
        <Network size={18} />
        <h2>多智能体协作</h2>
        <span className="acp-evidence-badge">证据 {model.evidenceCount}</span>
      </div>

      <div className="acp-stage-timeline">
        {model.stages.map((stage) => (
          <div className={`acp-stage acp-${stage.status}`} key={stage.key}>
            <StageIcon status={stage.status} />
            <div className="acp-stage-body">
              <div className="acp-stage-head">
                <strong>{stage.label}</strong>
                {stage.modelTier ? (
                  <span className="acp-model-tier">
                    <Cpu size={12} />
                    {stage.modelTier}
                  </span>
                ) : null}
                {typeof stage.score === "number" ? (
                  <span className="acp-score">{stage.score.toFixed(2)}</span>
                ) : null}
              </div>
              <p>{stage.detail}</p>
              <small className="acp-agent-name">{stage.agent}</small>
            </div>
          </div>
        ))}
      </div>

      <div className="acp-subtitle">
        <GitBranch size={15} />
        <h3>六个生成分支</h3>
      </div>
      <div className="acp-branches">
        {model.branches.map((branch) => (
          <div className={`acp-branch acp-branch-${branch.status}`} key={branch.type}>
            <StageIcon status={branch.status} />
            <div>
              <strong>{branch.label}</strong>
              <small>{branch.title || resourceBranchLabels[branch.type]}</small>
            </div>
          </div>
        ))}
      </div>

      <div className="acp-subtitle">
        <Sparkles size={15} />
        <h3>为什么推荐这个资源</h3>
      </div>
      <div className="acp-explain">
        <div className="acp-explain-dimensions">
          {model.explainability.profileDimensions.length ? (
            model.explainability.profileDimensions.map((item) => (
              <div className="acp-dimension" key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))
          ) : (
            <p className="empty">等待画像数据。</p>
          )}
        </div>
        <div className="acp-graph-relations">
          <div className="acp-relation">
            <span>当前节点</span>
            <strong>{model.explainability.currentNode || "—"}</strong>
          </div>
          <div className="acp-relation">
            <span>前置</span>
            <strong>{model.explainability.predecessors.join("、") || "无"}</strong>
          </div>
          <div className="acp-relation">
            <span>后继</span>
            <strong>{model.explainability.successors.join("、") || "无"}</strong>
          </div>
          <div className="acp-relation">
            <span>引用 chunk</span>
            <strong>{model.explainability.citationCount} 处</strong>
          </div>
        </div>
      </div>

      <div className={`acp-mastery mastery-${model.mastery}`}>
        <span className="acp-mastery-dot" />
        <strong>节点掌握度 · {masteryLabels[model.mastery]}</strong>
        {model.decision ? <small>{model.decision}</small> : null}
      </div>
    </section>
  );
}
