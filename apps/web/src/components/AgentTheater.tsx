import { useState } from "react";
import { BrainCircuit, CheckCircle2, XCircle, Zap } from "lucide-react";
import type { WorkflowPackage, ResourceType } from "../api/client";
import { buildAgentCollaboration } from "./agentCollaborationModel";
import {
  buildTheaterGraph,
  buildTheaterTraceCard,
  theaterNodeClassName,
  theaterStatusText,
  THEATER_HEIGHT,
  THEATER_WIDTH,
  type TheaterNode
} from "./agentTheaterModel";

/**
 * 多智能体协作剧场：引擎态视觉样板间。
 * 以发光节点网络呈现「规划→检索→6 分支并行生成→事实校验→教学适配→双模型辩论→决策」全链路，
 * 节点可点击展开该阶段的可解释 trace。
 */
export function AgentTheater({
  pkg,
  running,
  requestedTypes = []
}: {
  pkg?: WorkflowPackage;
  running: boolean;
  requestedTypes?: ResourceType[];
}) {
  const vm = buildAgentCollaboration(pkg, running, requestedTypes);
  const graph = buildTheaterGraph(vm);
  const [selectedKey, setSelectedKey] = useState<string>("decision");
  const trace = buildTheaterTraceCard(vm, selectedKey);

  function handleNodeClick(node: TheaterNode) {
    if (!node.isBranch) {
      setSelectedKey(node.key);
    }
  }

  return (
    <section className="agent-theater" aria-label="多智能体协作剧场">
      <div className="theater-head">
        <BrainCircuit size={17} />
        <h3>多智能体协作剧场</h3>
        <span className="theater-live-dot" aria-hidden="true" />
        <span className="theater-head-meta">
          {running ? "工作流执行中" : vm.decision ? `最终决策：${vm.decision}` : "等待资源生成"}
        </span>
      </div>

      <div className="theater-stage">
        <svg
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="智能体协作网络图"
          viewBox={`0 0 ${THEATER_WIDTH} ${THEATER_HEIGHT}`}
        >
          <defs>
            <radialGradient cx="50%" cy="50%" id="theater-glow" r="50%">
              <stop offset="0%" stopColor="rgba(129,140,248,0.9)" />
              <stop offset="100%" stopColor="rgba(129,140,248,0)" />
            </radialGradient>
          </defs>

          {graph.links.map((link) => {
            const from = graph.nodes.find((node) => node.key === link.from);
            const to = graph.nodes.find((node) => node.key === link.to);
            if (!from || !to) {
              return null;
            }
            const active = from.status === "done" && to.status !== "pending";
            return (
              <g key={`${link.from}-${link.to}`}>
                <line
                  className={`theater-link ${link.kind} ${active ? "active" : ""}`}
                  x1={from.x}
                  x2={to.x}
                  y1={from.y}
                  y2={to.y}
                />
                {active ? (
                  <circle r={link.kind === "main" ? 3.5 : 2.4}>
                    <animateMotion
                      dur={link.kind === "main" ? "2.4s" : "1.8s"}
                      path={`M ${from.x} ${from.y} L ${to.x} ${to.y}`}
                      repeatCount="indefinite"
                    />
                  </circle>
                ) : null}
              </g>
            );
          })}

          {graph.nodes.map((node) => {
            const selected = node.key === selectedKey;
            const status = theaterStatusText(node);
            return (
              <g
                className={theaterNodeClassName(node)}
                key={node.key}
                onClick={() => handleNodeClick(node)}
                role="button"
                tabIndex={node.isBranch ? -1 : 0}
              >
                {node.status === "done" && !node.isBranch ? (
                  <circle cx={node.x} cy={node.y} fill="url(#theater-glow)" opacity={0.55} r={node.radius * 1.9} />
                ) : null}
                <circle
                  className="theater-node-circle"
                  cx={node.x}
                  cy={node.y}
                  r={node.radius}
                />
                {node.dualModel ? (
                  <>
                    <circle className="theater-dual-a" cx={node.x - 9} cy={node.y - 4} r={7} />
                    <circle className="theater-dual-b" cx={node.x + 9} cy={node.y - 4} r={7} />
                    <text className="theater-dual-x" x={node.x} y={node.y - 2}>×</text>
                  </>
                ) : null}
                <text className="theater-node-label" x={node.x} y={node.y + (node.isBranch ? 3.5 : 4)}>
                  {node.isBranch ? node.label.slice(0, 2) : node.label}
                </text>
                {!node.isBranch ? (
                  <text className={`theater-node-status ${node.status}`} x={node.x} y={node.y + node.radius + 16}>
                    {status}
                  </text>
                ) : null}
                {selected && !node.isBranch ? (
                  <rect
                    className="theater-selected-ring"
                    height={(node.radius + 7) * 2}
                    rx={node.radius + 7}
                    width={(node.radius + 7) * 2.4}
                    x={node.x - (node.radius + 7) * 1.2}
                    y={node.y - (node.radius + 7)}
                  />
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="theater-legend">
        <span><i className="dot done" />已完成</span>
        <span><i className="dot running" />运行中</span>
        <span><i className="dot pending" />待启动</span>
        <span><i className="dot failed" />已驳回</span>
        <span className="theater-legend-note">点击节点查看该阶段 trace</span>
      </div>

      {trace.stage ? (
        <div className={`theater-trace is-${trace.stage.status}`}>
          <div className="theater-trace-head">
            {trace.stage.status === "failed" ? <XCircle size={15} /> : trace.stage.status === "done" ? <CheckCircle2 size={15} /> : <Zap size={15} />}
            <strong>{trace.stage.label}</strong>
            <em>{trace.stage.agent}</em>
            {trace.stage.modelTier ? <em className="model-tier">{trace.stage.modelTier}</em> : null}
            {trace.stage.score !== undefined ? <em className="score">{Math.round(trace.stage.score * 100)} 分</em> : null}
          </div>
          <p>{trace.stage.detail}</p>
          {trace.branches.length ? (
            <div className="theater-trace-branches">
              {trace.branches.map((branch) => (
                <span key={branch.label} className={branch.status === "done" ? "done" : ""}>
                  {branch.label}
                  {branch.title ? <i>{branch.title}</i> : null}
                </span>
              ))}
            </div>
          ) : null}
          <div className="theater-trace-foot">
            <span>证据块 {trace.citationCount} 条 · 图谱约束注入</span>
            {trace.decision ? <strong>决策：{trace.decision}</strong> : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
