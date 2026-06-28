import { useEffect, useMemo, useRef, useState } from "react";
import { GitBranch, Network, RefreshCw, Route, Sparkles, Target } from "lucide-react";
import {
  buildKnowledgeGraph,
  getKnowledgeGraph,
  type Course,
  type KnowledgeGraph
} from "../api/client";
import { isLearnableKnowledgeNode } from "../pages/knowledgeLearningRouteStateModel";

interface KnowledgeGraphPanelProps {
  token: string;
  course: Course;
  onNodeOpen?: (node: GraphRecord) => void;
}

type GraphRecord = Record<string, unknown>;
type Point = { x: number; y: number };
type LayoutNode = {
  id: string;
  node: GraphRecord;
  point: Point;
  radius: number;
  depth: number;
  degree: number;
};
type GraphLayout = {
  width: number;
  height: number;
  nodes: LayoutNode[];
  positions: Map<string, LayoutNode>;
  edges: GraphRecord[];
  rootId: string;
};
type MasteryStatus = "not_started" | "severe_weak" | "basic" | "good" | "proficient";
type MasteryInfo = {
  status: MasteryStatus;
  label: string;
  score?: number;
};

const relationLabels: Record<string, string> = {
  prerequisite: "前置",
  contains: "包含",
  applies_to: "应用",
  common_mistake: "易错",
  case_supports: "案例"
};
const nodeTypeLabels: Record<string, string> = {
  concept: "概念",
  method: "方法",
  formula: "公式",
  tool: "工具",
  case: "案例"
};
const difficultyLabels: Record<string, string> = {
  basic: "基础",
  intermediate: "进阶",
  advanced: "高级"
};
const masteryLabels: Record<MasteryStatus, string> = {
  not_started: "未学习",
  severe_weak: "严重弱项",
  basic: "掌握基础",
  good: "达标良好",
  proficient: "精通"
};
const masteryLegendItems: Array<{ status: MasteryStatus; label: string }> = [
  { status: "not_started", label: "未学习" },
  { status: "severe_weak", label: "严重弱项" },
  { status: "basic", label: "掌握基础" },
  { status: "good", label: "达标良好" },
  { status: "proficient", label: "精通" }
];
const masteryStatusAliases: Record<string, MasteryStatus> = {
  default: "not_started",
  none: "not_started",
  not_started: "not_started",
  unlearned: "not_started",
  未学习: "not_started",
  weak: "severe_weak",
  severe_weak: "severe_weak",
  severe_weakness: "severe_weak",
  failed: "severe_weak",
  fail: "severe_weak",
  red: "severe_weak",
  严重弱项: "severe_weak",
  弱项: "severe_weak",
  不达标: "severe_weak",
  basic: "basic",
  foundation: "basic",
  orange: "basic",
  掌握基础: "basic",
  基础: "basic",
  good: "good",
  qualified: "good",
  pass: "good",
  passed: "good",
  light_green: "good",
  达标良好: "good",
  达标: "good",
  良好: "good",
  proficient: "proficient",
  mastery: "proficient",
  mastered: "proficient",
  expert: "proficient",
  green: "proficient",
  精通: "proficient"
};
const nodeTypeOrder: Record<string, number> = {
  concept: 0,
  method: 1,
  formula: 2,
  tool: 3,
  case: 4
};

function textValue(record: GraphRecord | undefined, key: string, fallback = ""): string {
  const value = record?.[key];
  return typeof value === "string" ? value : fallback;
}

function numberValue(record: GraphRecord | undefined, key: string, fallback = 0): number {
  const value = record?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function optionalNumberValue(record: GraphRecord | undefined, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record?.[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim()) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return undefined;
}

function stringArrayValue(record: GraphRecord | undefined, key: string): string[] {
  const value = record?.[key];
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function nodeId(node: GraphRecord | undefined, fallback = ""): string {
  return textValue(node, "id", fallback);
}

function nodeName(node: GraphRecord | undefined, fallback = "未命名知识点"): string {
  return textValue(node, "name", textValue(node, "id", fallback));
}

function shortText(value: string, maxLength = 14): string {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}...` : value;
}

function labelFor(map: Record<string, string>, value: string, fallback: string): string {
  return map[value] ?? fallback;
}

function confidenceText(value: number): string {
  if (!Number.isFinite(value)) {
    return "0%";
  }
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

function normalizeMasteryStatus(value: string): MasteryStatus | undefined {
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  return masteryStatusAliases[normalized] ?? masteryStatusAliases[value.trim()];
}

function masteryStatusFromScore(score: number): MasteryStatus {
  const normalizedScore = score > 1 ? score / 100 : score;
  if (normalizedScore < 0.6) {
    return "severe_weak";
  }
  if (normalizedScore < 0.75) {
    return "basic";
  }
  if (normalizedScore < 0.9) {
    return "good";
  }
  return "proficient";
}

function masteryInfo(node: GraphRecord | undefined): MasteryInfo {
  const explicitStatus = [
    "mastery_status",
    "masteryStatus",
    "learning_status",
    "learningStatus",
    "mastery_level",
    "masteryLevel"
  ]
    .map((key) => textValue(node, key))
    .find(Boolean);
  const normalizedStatus = explicitStatus ? normalizeMasteryStatus(explicitStatus) : undefined;
  const score = optionalNumberValue(node, ["mastery_score", "masteryScore", "mastery", "score", "assessment_score"]);
  const status = normalizedStatus ?? (score === undefined ? "not_started" : masteryStatusFromScore(score));
  return {
    status,
    label: masteryLabels[status],
    score
  };
}

function masteryText(info: MasteryInfo): string {
  if (info.score === undefined) {
    return info.label;
  }
  return `${info.label} ${confidenceText(info.score > 1 ? info.score / 100 : info.score)}`;
}

function compareNodes(left: GraphRecord, right: GraphRecord): number {
  const leftLevel = numberValue(left, "level", 0);
  const rightLevel = numberValue(right, "level", 0);
  const leftOrder = numberValue(left, "order", 0);
  const rightOrder = numberValue(right, "order", 0);
  const leftType = nodeTypeOrder[textValue(left, "node_type")] ?? 9;
  const rightType = nodeTypeOrder[textValue(right, "node_type")] ?? 9;
  if (leftLevel !== rightLevel) {
    return leftLevel - rightLevel;
  }
  if (leftOrder !== rightOrder) {
    return leftOrder - rightOrder;
  }
  if (leftType !== rightType) {
    return leftType - rightType;
  }
  return nodeName(left).localeCompare(nodeName(right), "zh-CN");
}

function sortedNodes(nodes: GraphRecord[]): GraphRecord[] {
  return [...nodes].filter((node) => nodeId(node)).sort(compareNodes);
}

function edgeId(edge: GraphRecord, index: number): string {
  return textValue(edge, "id", `edge-${index}`);
}

function relationLabel(edge: GraphRecord): string {
  return labelFor(relationLabels, textValue(edge, "relation_type"), "关联");
}

function validGraphEdges(edges: GraphRecord[], nodeById: Map<string, GraphRecord>): GraphRecord[] {
  return edges.filter((edge) => {
    const sourceId = textValue(edge, "source_node_id");
    const targetId = textValue(edge, "target_node_id");
    return sourceId !== targetId && nodeById.has(sourceId) && nodeById.has(targetId);
  });
}

function chooseRootId(nodes: GraphRecord[], degree: Map<string, number>): string {
  const explicitRoot = nodes.find((node) => numberValue(node, "level", 0) === 0);
  if (explicitRoot) {
    return nodeId(explicitRoot);
  }
  const rankedNodes = [...nodes].sort((left, right) => {
    const degreeDiff = (degree.get(nodeId(right)) ?? 0) - (degree.get(nodeId(left)) ?? 0);
    return degreeDiff || compareNodes(left, right);
  });
  return nodeId(rankedNodes[0]);
}

function buildGraphLayout(nodes: GraphRecord[], rawEdges: GraphRecord[]): GraphLayout {
  const orderedNodes = sortedNodes(nodes);
  const nodeById = new Map(orderedNodes.map((node) => [nodeId(node), node]));
  const edges = validGraphEdges(rawEdges, nodeById);
  const adjacency = new Map<string, Set<string>>();
  const degree = new Map<string, number>();

  orderedNodes.forEach((node) => {
    const id = nodeId(node);
    adjacency.set(id, new Set());
    degree.set(id, 0);
  });

  edges.forEach((edge) => {
    const sourceId = textValue(edge, "source_node_id");
    const targetId = textValue(edge, "target_node_id");
    adjacency.get(sourceId)?.add(targetId);
    adjacency.get(targetId)?.add(sourceId);
    degree.set(sourceId, (degree.get(sourceId) ?? 0) + 1);
    degree.set(targetId, (degree.get(targetId) ?? 0) + 1);
  });

  const rootId = chooseRootId(orderedNodes, degree);
  const depths = new Map<string, number>();
  const queue: string[] = [];
  if (rootId) {
    depths.set(rootId, 0);
    queue.push(rootId);
  }

  while (queue.length > 0) {
    const currentId = queue.shift() as string;
    const currentDepth = depths.get(currentId) ?? 0;
    (adjacency.get(currentId) ?? new Set()).forEach((nextId) => {
      if (depths.has(nextId)) {
        return;
      }
      depths.set(nextId, Math.min(currentDepth + 1, 5));
      queue.push(nextId);
    });
  }

  orderedNodes.forEach((node) => {
    const id = nodeId(node);
    if (depths.has(id)) {
      return;
    }
    const fallbackDepth = Math.max(1, Math.min(5, numberValue(node, "level", 2)));
    depths.set(id, fallbackDepth);
  });

  const groups = new Map<number, GraphRecord[]>();
  orderedNodes.forEach((node) => {
    const depth = depths.get(nodeId(node)) ?? 1;
    groups.set(depth, [...(groups.get(depth) ?? []), node]);
  });
  groups.forEach((group, depth) => {
    groups.set(
      depth,
      [...group].sort((left, right) => {
        const degreeDiff = (degree.get(nodeId(right)) ?? 0) - (degree.get(nodeId(left)) ?? 0);
        return degreeDiff || compareNodes(left, right);
      })
    );
  });

  const largestGroup = Math.max(1, ...[...groups.values()].map((group) => group.length));
  const width = Math.max(980, Math.min(2200, 900 + largestGroup * 42 + orderedNodes.length * 4));
  const height = Math.max(560, Math.min(1300, 520 + Math.ceil(orderedNodes.length / 18) * 92));
  const center = { x: width / 2, y: height / 2 - 12 };
  const maxRadius = Math.min(width * 0.45, height * 0.68);
  const positions = new Map<string, LayoutNode>();

  [...groups.keys()].sort((left, right) => left - right).forEach((depth) => {
    const group = groups.get(depth) ?? [];
    if (depth === 0) {
      group.forEach((node) => {
        const id = nodeId(node);
        positions.set(id, {
          id,
          node,
          point: center,
          radius: 24,
          depth,
          degree: degree.get(id) ?? 0
        });
      });
      return;
    }

    const baseRadius = Math.min(maxRadius, 115 + depth * 125);
    const maxPerRing = Math.max(8, Math.floor((2 * Math.PI * baseRadius) / 142));
    group.forEach((node, index) => {
      const id = nodeId(node);
      const ringIndex = Math.floor(index / maxPerRing);
      const indexInRing = index % maxPerRing;
      const ringCount = Math.min(maxPerRing, group.length - ringIndex * maxPerRing);
      const radius = Math.min(maxRadius + 80, baseRadius + ringIndex * 86);
      const angle = -Math.PI / 2 + (2 * Math.PI * indexInRing) / Math.max(1, ringCount) + depth * 0.22 + ringIndex * 0.13;
      const nodeDegree = degree.get(id) ?? 0;
      positions.set(id, {
        id,
        node,
        point: {
          x: Math.max(48, Math.min(width - 48, center.x + Math.cos(angle) * radius)),
          y: Math.max(54, Math.min(height - 70, center.y + Math.sin(angle) * radius * 0.72))
        },
        radius: Math.max(13, Math.min(24, 14 + nodeDegree * 1.8)),
        depth,
        degree: nodeDegree
      });
    });
  });

  return {
    width,
    height,
    nodes: [...positions.values()].sort((left, right) => left.depth - right.depth || right.degree - left.degree),
    positions,
    edges,
    rootId
  };
}

function defaultSelectedNodeId(nodes: GraphRecord[], edges: GraphRecord[]): string {
  const layout = buildGraphLayout(nodes, edges);
  return layout.rootId || layout.nodes[0]?.id || "";
}

function isLearnableNode(node: GraphRecord | undefined): boolean {
  return isLearnableKnowledgeNode(node, nodeId(node));
}

function nodeRelations(nodeIdValue: string, graph: KnowledgeGraph, nodeById: Map<string, GraphRecord>) {
  const related = graph.edges.filter((edge) => {
    return textValue(edge, "source_node_id") === nodeIdValue || textValue(edge, "target_node_id") === nodeIdValue;
  });
  const incoming = related.filter((edge) => textValue(edge, "target_node_id") === nodeIdValue);
  const outgoing = related.filter((edge) => textValue(edge, "source_node_id") === nodeIdValue);
  const prerequisites = incoming.filter((edge) => textValue(edge, "relation_type") === "prerequisite");
  const nextSteps = outgoing.filter((edge) => textValue(edge, "relation_type") === "prerequisite");
  const applications = related.filter((edge) => ["applies_to", "case_supports"].includes(textValue(edge, "relation_type")));
  const mistakes = related.filter((edge) => textValue(edge, "relation_type") === "common_mistake");
  const contains = outgoing.filter((edge) => textValue(edge, "relation_type") === "contains");

  return {
    related,
    incoming,
    outgoing,
    prerequisites,
    nextSteps,
    applications,
    mistakes,
    contains,
    describe(edge: GraphRecord): string {
      const source = nodeById.get(textValue(edge, "source_node_id"));
      const target = nodeById.get(textValue(edge, "target_node_id"));
      return `${nodeName(source, "起点")} → ${nodeName(target, "终点")}`;
    }
  };
}

function RelationList({ edges, emptyText, title, describe }: {
  edges: GraphRecord[];
  emptyText: string;
  title: string;
  describe: (edge: GraphRecord) => string;
}) {
  return (
    <div className="graph-description-block">
      <strong>{title}</strong>
      {edges.length > 0 ? (
        <ul>
          {edges.slice(0, 6).map((edge, index) => (
            <li key={edgeId(edge, index)}>
              <span>{relationLabel(edge)}</span>
              <p>{describe(edge)}</p>
              {textValue(edge, "reason") ? <small>{textValue(edge, "reason")}</small> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="graph-description-empty">{emptyText}</p>
      )}
    </div>
  );
}

export function KnowledgeGraphPanel({ token, course, onNodeOpen }: KnowledgeGraphPanelProps) {
  const [graph, setGraph] = useState<KnowledgeGraph>({ nodes: [], edges: [] });
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState("");
  const courseIdRef = useRef(course.id);
  const graphRequestRef = useRef(0);
  const graphLoadRequestRef = useRef(0);
  const graphBuildRequestRef = useRef(0);

  async function loadGraph() {
    const requestCourseId = course.id;
    const requestId = graphRequestRef.current + 1;
    graphRequestRef.current = requestId;
    const loadRequestId = graphLoadRequestRef.current + 1;
    graphLoadRequestRef.current = loadRequestId;
    setLoading(true);
    setError("");
    try {
      const nextGraph = await getKnowledgeGraph(token, requestCourseId);
      if (courseIdRef.current !== requestCourseId || graphRequestRef.current !== requestId) {
        return;
      }
      setGraph(nextGraph);
      setSelectedNodeId((current) => {
        if (nextGraph.nodes.some((node) => nodeId(node) === current)) {
          return current;
        }
        return defaultSelectedNodeId(nextGraph.nodes, nextGraph.edges);
      });
    } catch (caught) {
      if (courseIdRef.current !== requestCourseId || graphRequestRef.current !== requestId) {
        return;
      }
      setError(caught instanceof Error ? caught.message : "加载知识图谱失败");
    } finally {
      if (courseIdRef.current === requestCourseId && graphLoadRequestRef.current === loadRequestId) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    courseIdRef.current = course.id;
    setGraph({ nodes: [], edges: [] });
    setSelectedNodeId("");
    setLoading(false);
    setBuilding(false);
    setError("");
    void loadGraph();
  }, [course.id]);

  async function handleBuild() {
    setBuilding(true);
    setError("");
    const requestCourseId = course.id;
    const requestId = graphRequestRef.current + 1;
    graphRequestRef.current = requestId;
    const buildRequestId = graphBuildRequestRef.current + 1;
    graphBuildRequestRef.current = buildRequestId;
    try {
      const nextGraph = await buildKnowledgeGraph(token, requestCourseId);
      if (courseIdRef.current !== requestCourseId || graphRequestRef.current !== requestId) {
        return;
      }
      setGraph(nextGraph);
      setSelectedNodeId(defaultSelectedNodeId(nextGraph.nodes, nextGraph.edges));
    } catch (caught) {
      if (courseIdRef.current !== requestCourseId || graphRequestRef.current !== requestId) {
        return;
      }
      setError(caught instanceof Error ? caught.message : "构建知识图谱失败");
    } finally {
      if (courseIdRef.current === requestCourseId && graphBuildRequestRef.current === buildRequestId) {
        setBuilding(false);
      }
    }
  }

  const layout = useMemo(() => buildGraphLayout(graph.nodes, graph.edges), [graph.nodes, graph.edges]);
  const nodeById = useMemo(() => new Map(graph.nodes.map((node) => [nodeId(node), node])), [graph.nodes]);
  const selectedNode = nodeById.get(selectedNodeId) ?? layout.nodes[0]?.node;
  const activeNodeId = selectedNode ? nodeId(selectedNode) : "";
  const selectedMastery = masteryInfo(selectedNode);
  const activeRelations = nodeRelations(activeNodeId, graph, nodeById);
  const connectedNodeIds = new Set<string>([
    activeNodeId,
    ...activeRelations.related.flatMap((edge) => [textValue(edge, "source_node_id"), textValue(edge, "target_node_id")])
  ]);
  const relationCounts = graph.edges.reduce<Record<string, number>>((counts, edge) => {
    const relation = textValue(edge, "relation_type", "unknown");
    counts[relation] = (counts[relation] ?? 0) + 1;
    return counts;
  }, {});

  return (
    <section className="kb-section graph-panel">
      <div className="kb-section-head graph-head">
        <div>
          <h3>知识图谱</h3>
          <p>{graph.nodes.length} 节点 / {graph.edges.length} 关系</p>
        </div>
        <div className="graph-actions">
          <button className="secondary-action" disabled={building} onClick={handleBuild} type="button">
            <GitBranch size={16} />
            {building ? "构建中" : "构建"}
          </button>
          <button className="icon-action" aria-label="刷新知识图谱" disabled={loading} onClick={loadGraph} type="button">
            <RefreshCw className={loading ? "spin" : ""} size={16} />
          </button>
        </div>
      </div>

      {error ? <div className="error compact-error">{error}</div> : null}

      {graph.nodes.length > 0 ? (
        <div className="graph-visual-layout">
          <div className="graph-map-shell">
            <div className="graph-map-toolbar">
              <div>
                <strong>{course.name} · 语义知识网络</strong>
                <span>由本地知识库内容抽取知识点、前置关系、应用关系和易错关系</span>
              </div>
              <div className="graph-legend" aria-label="掌握情况图例">
                {masteryLegendItems.map((item) => (
                  <span className={`legend-node mastery-${item.status}`} key={item.status}>{item.label}</span>
                ))}
              </div>
            </div>
            <div className="graph-map-scroll">
              <svg
                aria-label="课程知识图谱可视化"
                className="knowledge-graph-svg"
                role="img"
                viewBox={`0 0 ${layout.width} ${layout.height}`}
              >
                <defs>
                  <marker id="kg-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
                    <path d="M0,0 L8,4 L0,8 z" fill="#7c8fa6" />
                  </marker>
                  <radialGradient id="kg-node-glow" cx="35%" cy="30%" r="70%">
                    <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
                    <stop offset="42%" stopColor="#5ee0bd" stopOpacity="0.92" />
                    <stop offset="100%" stopColor="#12846f" stopOpacity="0.95" />
                  </radialGradient>
                </defs>

                {layout.edges.map((edge, index) => {
                  const source = layout.positions.get(textValue(edge, "source_node_id"));
                  const target = layout.positions.get(textValue(edge, "target_node_id"));
                  if (!source || !target) {
                    return null;
                  }
                  const selected = activeNodeId && (
                    source.id === activeNodeId ||
                    target.id === activeNodeId
                  );
                  const dimmed = activeNodeId && !selected && (!connectedNodeIds.has(source.id) || !connectedNodeIds.has(target.id));
                  const midX = (source.point.x + target.point.x) / 2;
                  const midY = (source.point.y + target.point.y) / 2;
                  const curve = Math.max(-70, Math.min(70, (target.point.y - source.point.y) * 0.18));
                  const relation = textValue(edge, "relation_type", "relation");
                  return (
                    <g className={`kg-edge-group ${selected ? "selected" : ""} ${dimmed ? "dimmed" : ""}`} key={edgeId(edge, index)}>
                      <path
                        className={`kg-edge relation-${relation}`}
                        d={`M ${source.point.x} ${source.point.y} Q ${midX + curve} ${midY - curve} ${target.point.x} ${target.point.y}`}
                        markerEnd="url(#kg-arrow)"
                      />
                      <title>{relationLabel(edge)}：{textValue(edge, "reason", activeRelations.describe(edge))}</title>
                      {selected ? (
                        <text className="kg-edge-label" x={midX} y={midY - 8}>
                          {relationLabel(edge)}
                        </text>
                      ) : null}
                    </g>
                  );
                })}

                {layout.nodes.map((layoutNode) => {
                  const type = textValue(layoutNode.node, "node_type", "concept");
                  const mastery = masteryInfo(layoutNode.node);
                  const selected = layoutNode.id === activeNodeId;
                  const connected = connectedNodeIds.has(layoutNode.id);
                  const dimmed = activeNodeId && !selected && !connected;
                  const label = selected || connected || graph.nodes.length <= 36
                    ? shortText(nodeName(layoutNode.node), selected ? 20 : 13)
                    : shortText(nodeName(layoutNode.node), 8);
                  return (
                    <g
                      aria-label={`${nodeName(layoutNode.node)}，${masteryText(mastery)}`}
                      className={`kg-node type-${type} mastery-${mastery.status} ${selected ? "selected" : ""} ${connected ? "connected" : ""} ${dimmed ? "dimmed" : ""}`}
                      key={layoutNode.id}
                      onClick={() => setSelectedNodeId(layoutNode.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedNodeId(layoutNode.id);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      transform={`translate(${layoutNode.point.x} ${layoutNode.point.y})`}
                    >
                      <title>{nodeName(layoutNode.node)}：{masteryText(mastery)}；{textValue(layoutNode.node, "summary", "暂无摘要")}</title>
                      {selected ? <circle className="kg-node-pulse" r={layoutNode.radius + 14} /> : null}
                      <circle className="kg-node-orbit" r={layoutNode.radius + 5} />
                      <circle className="kg-node-core" r={layoutNode.radius} />
                      <text className="kg-node-label" y={layoutNode.radius + 18}>{label}</text>
                    </g>
                  );
                })}
              </svg>
            </div>
          </div>

          <div className="graph-description-panel">
            {selectedNode ? (
              <>
                <div className="graph-description-head">
                  <div>
                    <span>{labelFor(nodeTypeLabels, textValue(selectedNode, "node_type", "concept"), "知识点")}</span>
                    <h4>{nodeName(selectedNode)}</h4>
                  </div>
                  <div className="graph-description-tags">
                    <span className={`mastery-tag mastery-${selectedMastery.status}`}>{masteryText(selectedMastery)}</span>
                    <span>{labelFor(difficultyLabels, textValue(selectedNode, "difficulty", "basic"), "基础")}</span>
                    <span>可信度 {confidenceText(numberValue(selectedNode, "confidence"))}</span>
                  </div>
                </div>

                <p className="graph-node-summary">{textValue(selectedNode, "summary", "暂无摘要")}</p>

                <div className="graph-description-grid">
                  <RelationList
                    describe={activeRelations.describe}
                    edges={activeRelations.prerequisites}
                    emptyText="暂无明确前置知识"
                    title="前置知识"
                  />
                  <RelationList
                    describe={activeRelations.describe}
                    edges={activeRelations.nextSteps}
                    emptyText="暂无明确后续知识"
                    title="后续学习"
                  />
                  <RelationList
                    describe={activeRelations.describe}
                    edges={[...activeRelations.applications, ...activeRelations.mistakes]}
                    emptyText="暂无应用或易错关系"
                    title="应用与易错"
                  />
                </div>

                <div className="graph-source-row">
                  <span>来源 chunks</span>
                  <strong>{stringArrayValue(selectedNode, "source_chunk_ids").join(", ") || "-"}</strong>
                </div>

                <div className="graph-description-actions">
                  <div className="graph-metrics">
                    <span><Sparkles size={14} /> {graph.nodes.length} 个知识点</span>
                    <span><Route size={14} /> {relationCounts.prerequisite ?? 0} 条前置关系</span>
                    <span><Target size={14} /> {(relationCounts.applies_to ?? 0) + (relationCounts.case_supports ?? 0)} 条应用关系</span>
                  </div>
                  {onNodeOpen && isLearnableNode(selectedNode) ? (
                    <button className="primary-action" onClick={() => onNodeOpen(selectedNode)} type="button">
                      进入知识点学习
                    </button>
                  ) : (
                    <span className="graph-description-empty">课程总览节点仅用于导航，请选择具体知识点。</span>
                  )}
                </div>
              </>
            ) : (
              <span className="empty">选择图谱节点查看文字说明</span>
            )}
          </div>
        </div>
      ) : (
        <div className="graph-workspace">
          <div className="graph-empty">
            <Network size={22} />
            <span>{loading ? "正在加载知识图谱" : "暂无图谱，先上传资料并构建"}</span>
          </div>
        </div>
      )}
    </section>
  );
}
