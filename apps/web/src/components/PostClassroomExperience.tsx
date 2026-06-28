import { useMemo, useState, type CSSProperties } from "react";
import {
  Box,
  CheckCircle2,
  Code2,
  FileText,
  GitBranch,
  ListChecks,
  Play,
  RotateCcw,
  ShieldCheck,
  Sparkles
} from "lucide-react";
import type { GraphConstraints, KnowledgeContextItem, Resource, StudentProfile } from "../api/client";
import {
  isInlineCodeRunSuccessful,
  learningFlowSteps,
  nextPostClassroomStage,
  type PostClassroomStage,
  runInlinePythonLikeCode
} from "./postClassroomExperienceModel";

interface PostClassroomExperienceProps {
  documentResource?: Resource;
  exerciseResource?: Resource;
  graphConstraints?: GraphConstraints;
  knowledgeContext: KnowledgeContextItem[];
  mindMap?: Resource;
  onAssessmentReady: () => void;
  profile?: StudentProfile;
  topic: string;
  unlocked: boolean;
}

type MapNode = {
  id: string;
  label: string;
  detail: string;
};

const stageMeta = Object.fromEntries(learningFlowSteps.map((step) => [step.key, step])) as Record<
  PostClassroomStage,
  { key: PostClassroomStage; label: string; detail: string }
>;

export function PostClassroomExperience({
  documentResource,
  exerciseResource,
  graphConstraints,
  knowledgeContext,
  mindMap,
  onAssessmentReady,
  profile,
  topic,
  unlocked
}: PostClassroomExperienceProps) {
  const [stage, setStage] = useState<PostClassroomStage>("study_artifacts");
  const [selectedMapNode, setSelectedMapNode] = useState("");
  const mapNodes = useMemo(() => buildMapNodes(topic, mindMap, graphConstraints, knowledgeContext), [
    graphConstraints,
    knowledgeContext,
    mindMap,
    topic
  ]);
  const currentMapNode = mapNodes.find((node) => node.id === selectedMapNode) ?? mapNodes[0];

  function advance() {
    const next = nextPostClassroomStage(stage);
    if (next === "assessment") {
      onAssessmentReady();
    }
    setStage(next);
  }

  function goToStage(next: PostClassroomStage) {
    if (next === "assessment") {
      onAssessmentReady();
    }
    setStage(next);
  }

  if (!unlocked) {
    return (
      <section className="panel post-classroom-panel locked">
        <div className="panel-title">
          <Sparkles size={18} />
          <h2>课后交互深化</h2>
          <span>等待课堂</span>
        </div>
        <p>
          OpenMAIC 标准课堂生成完成后，将解锁文档笔记、思维导图、题库测试和浏览器代码运行。学习完成后进入评估，评估结果会写回知识图谱节点掌握状态并驱动路径重规划。
        </p>
      </section>
    );
  }

  return (
    <section className="panel post-classroom-panel" data-testid="post-classroom-experience">
      <div className="panel-title">
        <Sparkles size={18} />
        <h2>多智能体学习闭环</h2>
        <span>{stageMeta[stage].label}</span>
      </div>
      <div className="post-stage-rail">
        {learningFlowSteps.map((item) => (
          <button
            className={stage === item.key ? "active" : ""}
            key={item.key}
            onClick={() => goToStage(item.key)}
            type="button"
          >
            <strong>{item.label}</strong>
            <span>{item.detail}</span>
          </button>
        ))}
      </div>

      {stage === "classroom" ? (
        <div className="post-assessment-ready classroom-step-card">
          <Sparkles size={24} />
          <div>
            <strong>课程学习已由上方 OpenMAIC 课堂承载</strong>
            <p>完成课堂学习后，继续生成本节课的文档笔记与思维导图，再进入题库测试和代码运行。</p>
          </div>
          <button className="primary-action compact-button" onClick={() => goToStage("study_artifacts")} type="button">
            进入学习产物
          </button>
        </div>
      ) : null}
      {stage === "study_artifacts" ? (
        <StudyArtifactsStage
          documentResource={documentResource}
          graphConstraints={graphConstraints}
          mapNodes={mapNodes}
          mindMap={mindMap}
          onAdvance={advance}
          onSelect={setSelectedMapNode}
          profile={profile}
          selectedNode={currentMapNode}
          topic={topic}
        />
      ) : null}
      {stage === "quiz_lab" ? (
        <QuizAndCodeLab exerciseResource={exerciseResource} onAdvance={advance} topic={topic} />
      ) : null}
      {stage === "assessment" ? (
        <div className="post-assessment-ready">
          <CheckCircle2 size={24} />
          <div>
            <strong>题库与代码练习完成，进入学习评估</strong>
            <p>评估面板会根据测试得分同步知识图谱颜色：未达标进入补救路径，达标后回到主线任务并继续下一知识点。</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function StudyArtifactsStage({
  documentResource,
  graphConstraints,
  mapNodes,
  mindMap,
  onAdvance,
  onSelect,
  profile,
  selectedNode,
  topic
}: {
  documentResource?: Resource;
  graphConstraints?: GraphConstraints;
  mapNodes: MapNode[];
  mindMap?: Resource;
  onAdvance: () => void;
  onSelect: (nodeId: string) => void;
  profile?: StudentProfile;
  selectedNode: MapNode;
  topic: string;
}) {
  return (
    <div className="study-artifacts-grid">
      <article className="artifact-note-card">
        <div className="artifact-card-heading">
          <FileText size={18} />
          <span>文档笔记 Agent</span>
        </div>
        <strong>{documentResource?.title || `${topic} 学习笔记`}</strong>
        <p>
          {summarizeResource(documentResource) ||
            "课堂学习完成后，文档 Agent 会基于 MySQL 原文证据、学生画像和知识图谱约束生成这节课的结构化笔记。"}
        </p>
        <div className="artifact-source-row">
          <span>画像</span>
          <span>{profile?.learning_style || "学习偏好"}</span>
          <span>图谱</span>
          <span>{graphConstraints?.parent?.name || "章节上下文"}</span>
        </div>
      </article>

      <InteractiveMindMap nodes={mapNodes} onSelect={onSelect} selectedId={selectedNode.id} topic={topic} />

      <Concept3DView currentNode={selectedNode} graphConstraints={graphConstraints} profile={profile} topic={topic} />

      <article className="artifact-decision-card">
        <ShieldCheck size={22} />
        <div>
          <strong>学习产物完成后进入题库测试</strong>
          <p>
            思维导图负责建立知识结构，3D 可视化负责把抽象关系直观化。完成后进入题库与代码运行，测试结果会写回图谱掌握状态。
          </p>
        </div>
        <button className="primary-action compact-button" onClick={onAdvance} type="button">
          <ListChecks size={16} />
          进入题库测试
        </button>
      </article>
    </div>
  );
}

function InteractiveMindMap({
  nodes,
  onSelect,
  selectedId,
  topic
}: {
  nodes: MapNode[];
  onSelect: (nodeId: string) => void;
  selectedId: string;
  topic: string;
}) {
  const selected = nodes.find((node) => node.id === selectedId) ?? nodes[0];

  return (
    <div className="interactive-map-card">
      <div className="artifact-card-heading">
        <GitBranch size={18} />
        <span>思维导图 Agent</span>
      </div>
      <div className="interactive-map-canvas compact">
        <button className="map-root-node" onClick={() => onSelect(nodes[0].id)} type="button">
          {topic}
        </button>
        <div className="map-spokes">
          {nodes.slice(0, 8).map((node, index) => (
            <button
              className={node.id === selected.id ? "active" : ""}
              key={node.id}
              onClick={() => onSelect(node.id)}
              style={mapNodePosition(index)}
              type="button"
            >
              <GitBranch size={14} />
              <span>{node.label}</span>
            </button>
          ))}
        </div>
      </div>
      <strong>{selected.label}</strong>
      <p>{selected.detail}</p>
    </div>
  );
}

function mapNodePosition(index: number): CSSProperties {
  const angle = (Math.PI * 2 * index) / 8 - Math.PI / 2;
  return {
    "--node-x": `${Math.cos(angle) * 185}px`,
    "--node-y": `${Math.sin(angle) * 135}px`
  } as CSSProperties;
}

function Concept3DView({
  currentNode,
  graphConstraints,
  profile,
  topic
}: {
  currentNode: MapNode;
  graphConstraints?: GraphConstraints;
  profile?: StudentProfile;
  topic: string;
}) {
  const parentName = graphConstraints?.parent?.name || "课程章节";
  const successors = graphConstraints?.successors?.slice(0, 3) ?? [];

  return (
    <div className="concept-3d-card">
      <div className="artifact-card-heading">
        <Box size={18} />
        <span>抽象概念可视化</span>
      </div>
      <div className="concept-3d-scene" aria-label={`${topic} 三维概念关系`}>
        <div className="axis-line x" />
        <div className="axis-line y" />
        <div className="axis-line z" />
        <div className="concept-cube core">
          <Box size={20} />
          <span>{topic}</span>
        </div>
        <div className="concept-cube parent">{parentName}</div>
        <div className="concept-cube detail">{currentNode.label}</div>
        <div className="concept-cube learner">{profile?.learning_style || "学习偏好"}</div>
      </div>
      <article className="visual-explain-card">
        <span>空间化解释</span>
        <strong>{currentNode.label}</strong>
        <p>
          中心节点代表当前知识点，后方节点表示章节上下文，右侧节点表示后继知识。抽象概念不再只是文本，而是能被观察的结构关系。
        </p>
        {successors.length ? (
          <div className="successor-pills">
            {successors.map((item) => <span key={item.id}>{item.name}</span>)}
          </div>
        ) : null}
      </article>
    </div>
  );
}

function QuizAndCodeLab({
  exerciseResource,
  onAdvance,
  topic
}: {
  exerciseResource?: Resource;
  onAdvance: () => void;
  topic: string;
}) {
  return (
    <div className="quiz-code-stage">
      <article className="quiz-card">
        <div className="artifact-card-heading">
          <ListChecks size={18} />
          <span>题库测试 Agent</span>
        </div>
        <strong>{exerciseResource?.title || `${topic} 随堂题库`}</strong>
        <p>
          {summarizeResource(exerciseResource) ||
            "题库 Agent 会基于课堂内容、图谱依赖和学生薄弱点生成选择题、简答题与代码题。"}
        </p>
        <div className="quiz-item-list">
          <span>概念判断</span>
          <span>迁移应用</span>
          <span>代码实操</span>
        </div>
      </article>
      <InlineCodeLab onAdvance={onAdvance} topic={topic} />
    </div>
  );
}

function InlineCodeLab({ onAdvance, topic }: { onAdvance: () => void; topic: string }) {
  const starter = `# ${topic}：边写边学\nname = "Python"\nscore = 40 + 2\nprint("Hello " + name)\nprint(score)`;
  const [code, setCode] = useState(starter);
  const [output, setOutput] = useState("点击运行，在浏览器内即时查看输出。");
  const [autoAdvancePending, setAutoAdvancePending] = useState(false);

  function runCode() {
    const nextOutput = runInlinePythonLikeCode(code);
    setOutput(nextOutput);
    if (isInlineCodeRunSuccessful(nextOutput)) {
      setAutoAdvancePending(true);
      window.setTimeout(onAdvance, 1200);
    }
  }

  return (
    <div className="inline-code-lab">
      <div className="code-editor-shell">
        <div className="code-toolbar">
          <span>Browser Code Lab</span>
          <div>
            <button className="secondary-action compact-button" onClick={() => setCode(starter)} type="button">
              <RotateCcw size={15} />
              重置
            </button>
            <button className="primary-action compact-button" onClick={runCode} type="button">
              <Play size={15} />
              运行
            </button>
          </div>
        </div>
        <textarea aria-label="在线编码编辑器" onChange={(event) => setCode(event.target.value)} value={code} />
      </div>
      <div className="code-output-panel">
        <span>即时输出</span>
        <pre>{output}</pre>
        {autoAdvancePending ? <p className="auto-advance-note">代码运行成功，正在自动进入评估环节。</p> : null}
        <button className="primary-action compact-button" onClick={onAdvance} type="button">
          <ListChecks size={16} />
          提交测试结果
        </button>
      </div>
    </div>
  );
}

function summarizeResource(resource?: Resource): string {
  if (!resource?.content) {
    return "";
  }
  return resource.content.replace(/[#*_`>-]/g, "").replace(/\s+/g, " ").trim().slice(0, 180);
}

function buildMapNodes(
  topic: string,
  mindMap: Resource | undefined,
  graphConstraints: GraphConstraints | undefined,
  knowledgeContext: KnowledgeContextItem[]
): MapNode[] {
  const sourceLines = mindMap?.content
    .split(/\r?\n/)
    .map((line) => line.replace(/^#+\s*/, "").replace(/^[-*]\s*/, "").replace(/^\d+\.\s*/, "").trim())
    .filter(Boolean) ?? [];
  const graphNodes = [
    graphConstraints?.parent?.name,
    ...(graphConstraints?.predecessors ?? []).map((item) => item.name),
    ...(graphConstraints?.successors ?? []).map((item) => item.name),
    ...(graphConstraints?.related ?? []).map((item) => item.name)
  ].filter(Boolean) as string[];
  const evidenceNodes = knowledgeContext
    .slice(0, 3)
    .map((item) => item.heading || item.source_locator)
    .filter(Boolean);
  const labels = Array.from(new Set([topic, ...sourceLines, ...graphNodes, ...evidenceNodes])).slice(0, 9);

  return labels.map((label, index) => ({
    id: `map-node-${index}`,
    label,
    detail: index === 0
      ? "这是本节课的中心知识点，后续导图、3D 和编码练习都围绕它展开。"
      : "该节点来自资源大纲、知识图谱约束或 MySQL 原文证据，用于帮助学习者建立结构化理解。"
  }));
}
