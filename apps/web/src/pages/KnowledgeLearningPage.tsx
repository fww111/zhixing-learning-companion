import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  Bot,
  Clock3,
  Code2,
  FileText,
  GitBranch,
  ListChecks,
  Loader2,
  Maximize2,
  PlayCircle,
  RefreshCw,
  Route,
  ShieldAlert,
  Video
} from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  createLearningProfileEvent,
  generateLearningPackage,
  getCourse,
  getKnowledgeGraph,
  pollOpenMAICClassroom,
  updateLessonState,
  type Course,
  type CourseLearningStage,
  type GraphConstraints,
  type KnowledgeContextItem,
  type Resource,
  type ResourceType,
  type StudentProfile,
  type WorkflowPackage
} from "../api/client";
import { AgentTheater } from "../components/AgentTheater";
import { AgentCollaborationPanel } from "../components/AgentCollaborationPanel";
import { AssessmentPanel } from "../components/AssessmentPanel";
import { MindMapViewer } from "../components/MindMapViewer";
import { ResourceCard } from "../components/ResourceCard";
import {
  isInlineCodeRunSuccessful,
  isOpenMAICQuizEvent,
  lessonStageLabel,
  lessonViewModeFromState,
  openmaicClassroomIframeAllow,
  runInlinePythonLikeCode,
  shouldOpenAssessmentForOpenMAICQuizEvent,
  shouldPersistLessonStageTransition,
  shouldUnlockPostClassroom
} from "../components/postClassroomExperienceModel";
import { executeCode } from "../components/codeExecutionModel";
import { DebugMentorPanel } from "../components/DebugMentorPanel";
import { CODE_RUN_FAILED_EVENT } from "../components/AttentionFloating";
import { lessonCodeLabViewModel } from "./lessonCodeLabModel";
import { buildLessonProfileEvent, type LessonTrackedAction } from "./learningProfileEventModel";
import {
  isLearnableKnowledgeNodeId,
  lessonGenerationResourceTypes,
  knowledgeLearningNavigationSignature,
  knowledgeLearningRouteState
} from "./knowledgeLearningRouteStateModel";
import { useAuth } from "../state/auth";

type LearningViewMode = "learn" | "assess";
type LessonResourcePanel = "document" | "mind_map" | "code_lab";

const resourceSequence: ResourceType[] = ["document", "mind_map", "exercise", "code_lab", "video", "reading"];
const resourceLabels: Record<ResourceType, string> = {
  mind_map: "思维导图",
  document: "讲解文档",
  video: "视频脚本",
  code_lab: "代码实操",
  exercise: "分层练习",
  reading: "拓展阅读"
};

const resourcePurposes: Record<ResourceType, string> = {
  mind_map: "先建立知识结构",
  document: "理解概念与误区",
  video: "用分镜形成直观演示",
  code_lab: "用代码验证理解",
  exercise: "检查掌握情况",
  reading: "补充迁移材料"
};

const resourceIcons: Record<ResourceType, typeof FileText> = {
  mind_map: GitBranch,
  document: FileText,
  video: Video,
  code_lab: Code2,
  exercise: ListChecks,
  reading: PlayCircle
};

const lessonResourcePanels: Array<{
  key: LessonResourcePanel;
  label: string;
  detail: string;
  type: ResourceType;
}> = [
  { key: "document", label: "该节课文档", detail: "课堂笔记与知识溯源", type: "document" },
  { key: "mind_map", label: "知识点思维导图", detail: "结构关系与章节约束", type: "mind_map" },
  { key: "code_lab", label: "编程练习", detail: "浏览器内即时运行", type: "code_lab" }
];

function textValue(record: Record<string, unknown> | undefined, key: string, fallback = ""): string {
  const value = record?.[key];
  return typeof value === "string" ? value : fallback;
}

function profileToConversation(profile: StudentProfile, node: Record<string, unknown> | undefined): string {
  const topic = textValue(node, "name", textValue(node, "id", "当前知识点"));
  const summary = textValue(node, "summary", "");
  return [
    `当前知识点：${topic}`,
    summary ? `知识点摘要：${summary}` : "",
    `专业年级：${profile.major} ${profile.grade}`,
    `学习目标：${profile.learning_goal}`,
    `知识基础：${profile.knowledge_foundation}`,
    `薄弱点：${profile.weak_points.join("、")}`,
    `学习偏好：${profile.learning_style}，资源偏好 ${profile.resource_preference.join("、")}`,
    `时间安排：${profile.time_preference}`,
    `评估偏好：${profile.assessment_preference}`,
    `图谱关注：${profile.knowledge_graph_focus.join("、")}`
  ].filter(Boolean).join("。");
}

function orderResources(resources: Resource[]): Resource[] {
  return [...resources].sort((left, right) => resourceSequence.indexOf(left.type) - resourceSequence.indexOf(right.type));
}

export function KnowledgeLearningPage() {
  const { courseId, nodeId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { profile, refreshProfile, token } = useAuth();
  const numericCourseId = Number(courseId);
  const decodedNodeId = decodeURIComponent(nodeId || "");
  const classroomFrameWrapRef = useRef<HTMLElement | null>(null);
  const learnableNode = isLearnableKnowledgeNodeId(decodedNodeId);
  const routeState = knowledgeLearningRouteState(
    location.state as { node?: Record<string, unknown>; resourceTypes?: ResourceType[]; stage?: CourseLearningStage } | null,
    decodedNodeId
  );
  const navigationSignature = knowledgeLearningNavigationSignature(
    location.state as { node?: Record<string, unknown>; resourceTypes?: ResourceType[]; stage?: CourseLearningStage } | null,
    decodedNodeId
  );
  const resourceTypes = routeState.resourceTypes;
  const requestedResourceTypes = lessonGenerationResourceTypes(resourceTypes);
  const [course, setCourse] = useState<Course>();
  const [node, setNode] = useState<Record<string, unknown> | undefined>(() => routeState.node);
  const [result, setResult] = useState<WorkflowPackage>();
  const [activeResourcePanel, setActiveResourcePanel] = useState<LessonResourcePanel>("document");
  const [viewMode, setViewMode] = useState<LearningViewMode>("learn");
  const [assessmentScoreSeed, setAssessmentScoreSeed] = useState(0.58);
  const [statusSaving, setStatusSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [bootLoading, setBootLoading] = useState(false);
  const [openmaicPolling, setOpenmaicPolling] = useState(false);
  const [openmaicPollError, setOpenmaicPollError] = useState("");
  const [error, setError] = useState("");
  const topic = textValue(node, "name", decodedNodeId || "知识点学习");
  const resources = useMemo(() => orderResources(result?.resources ?? []), [result]);
  const mindMapResource = resources.find((resource) => resource.type === "mind_map");
  const documentResource = resources.find((resource) => resource.type === "document");
  const exerciseResource = resources.find((resource) => resource.type === "exercise");
  const codeLabResource = resources.find((resource) => resource.type === "code_lab");
  const openmaicClassroom = result?.openmaic_classroom;
  const openmaicUrl = openmaicClassroom?.url || (openmaicClassroom?.classroom_id ? `http://127.0.0.1:3000/classroom/${openmaicClassroom.classroom_id}` : "");
  const postClassroomUnlocked = shouldUnlockPostClassroom(
    openmaicClassroom?.status,
    openmaicUrl,
    openmaicClassroom?.classroom_id
  );
  const assessmentThreshold = 0.75;
  const knowledgeContext = result?.knowledge_context ?? [];
  const graphConstraints = result?.graph_constraints;
  const retrievalTrace = result?.retrieval_trace ?? [];
  const analysisPlan = result?.analysis_plan;
  const verificationReport = result?.verification_report;
  const pedagogyReport = result?.pedagogy_report;
  const debateReport = result?.debate_report;
  const decisionReport = result?.decision_report;
  const openmaicStatus = (openmaicClassroom?.status || "").toLowerCase();
  const openmaicHasTerminalError = ["failed", "error"].includes(openmaicStatus);
  const lessonState = result?.lesson_state;
  const sceneIndex = viewMode === "assess" ? 5 : lessonState?.classroom_completed ? 4 : 3;

  useEffect(() => {
    if (!learnableNode) {
      setCourse(undefined);
      setNode(undefined);
      setResult(undefined);
      setBootLoading(false);
      setLoading(false);
      setError("请从具体知识点进入学习页面，课程总览节点不支持直接生成课堂。");
      return;
    }
    if (!Number.isFinite(numericCourseId)) {
      setError("课程 ID 无效");
      return;
    }
    setBootLoading(true);
    setError("");
    Promise.all([
      getCourse(token, numericCourseId),
      node ? Promise.resolve(undefined) : getKnowledgeGraph(token, numericCourseId).catch(() => undefined)
    ])
      .then(([nextCourse, graph]) => {
        setCourse(nextCourse);
        if (!node && graph) {
          const foundNode = graph.nodes.find((item) => textValue(item, "id") === decodedNodeId);
          setNode(foundNode);
        }
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "加载知识点失败"))
      .finally(() => setBootLoading(false));
  }, [decodedNodeId, learnableNode, node, numericCourseId, token]);

  async function generate(options: { forceRegenerate?: boolean } = {}) {
    if (!profile) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const nextPackage = await generateLearningPackage({
        conversation: profileToConversation(profile, node),
        topic,
        course_id: numericCourseId,
        node_id: decodedNodeId,
        resource_types: requestedResourceTypes,
        force_regenerate: Boolean(options.forceRegenerate)
      }, token);
      setResult(nextPackage);
      setViewMode(lessonViewModeFromState(nextPackage.lesson_state));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "生成知识点学习资源失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (learnableNode && profile && course && !result && !loading && !bootLoading) {
      void generate();
    }
  }, [profile, course, bootLoading, topic, requestedResourceTypes, learnableNode]);

  useEffect(() => {
    setNode(routeState.node);
    setViewMode("learn");
    setResult(undefined);
    setActiveResourcePanel("document");
    setAssessmentScoreSeed(0.58);
    setError("");
  }, [numericCourseId, navigationSignature, routeState.node]);

  async function persistLessonState(patch: {
    current_stage?: string;
    classroom_completed?: boolean;
    notes_completed?: boolean;
    mind_map_completed?: boolean;
    code_lab_completed?: boolean;
    test_completed?: boolean;
    assessment_completed?: boolean;
    score?: number | null;
    openmaic_classroom?: typeof openmaicClassroom;
  }) {
    if (!Number.isFinite(numericCourseId) || !decodedNodeId) {
      return;
    }
    const nextPatch = { ...patch };
    if (
      nextPatch.current_stage
      && result?.lesson_state
      && !shouldPersistLessonStageTransition(result.lesson_state.current_stage, nextPatch.current_stage)
    ) {
      delete nextPatch.current_stage;
    }
    setStatusSaving(true);
    try {
      const nextState = await updateLessonState(token, {
        course_id: numericCourseId,
        node_id: decodedNodeId,
        ...nextPatch
      });
      setResult((current) => current ? { ...current, lesson_state: nextState } : current);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存课堂状态失败");
    } finally {
      setStatusSaving(false);
    }
  }

  async function recordLessonProfileEvent(input: {
    action: LessonTrackedAction;
    detail?: string;
    payload?: Record<string, unknown>;
    score?: number;
  }) {
    if (!Number.isFinite(numericCourseId) || !decodedNodeId) {
      return;
    }
    try {
      await createLearningProfileEvent(
        token,
        numericCourseId,
        buildLessonProfileEvent({
          action: input.action,
          detail: input.detail,
          nodeId: decodedNodeId,
          payload: input.payload,
          score: input.score,
          topic
        })
      );
      await refreshProfile(numericCourseId).catch(() => undefined);
    } catch {
      // Learning analytics must never block the lesson flow.
    }
  }

  async function completeClassroom() {
    await persistLessonState({
      current_stage: "test",
      classroom_completed: true
    });
    await recordLessonProfileEvent({
      action: "classroom_completed",
      payload: {
        classroom_id: openmaicClassroom?.classroom_id || "",
        job_id: openmaicClassroom?.job_id || "",
        status: openmaicClassroom?.status || ""
      }
    });
    setViewMode("assess");
  }

  useEffect(() => {
    function handleOpenMAICMessage(event: MessageEvent) {
      if (!isOpenMAICQuizEvent(event.data)) {
        return;
      }
      const classroomOrigin = openmaicUrl ? new URL(openmaicUrl, window.location.href).origin : "";
      if (classroomOrigin && event.origin !== classroomOrigin) {
        return;
      }
      if (shouldOpenAssessmentForOpenMAICQuizEvent(event.data.type)) {
        void persistLessonState({
          current_stage: "test",
          classroom_completed: true
        });
        setViewMode("assess");
        window.setTimeout(focusAssessmentPanel, 120);
      }
    }

    window.addEventListener("message", handleOpenMAICMessage);
    return () => window.removeEventListener("message", handleOpenMAICMessage);
  }, [openmaicUrl, numericCourseId, decodedNodeId, result?.lesson_state?.current_stage]);

  async function requestClassroomFullscreen() {
    const element = classroomFrameWrapRef.current;
    if (!element) {
      return;
    }
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
        return;
      }
      await element.requestFullscreen();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法进入课堂全屏播放，请检查浏览器全屏权限。");
    }
  }

  function focusAssessmentPanel() {
    document.getElementById("lesson-assessment-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function completeAssessment(score: number) {
    await persistLessonState({
      current_stage: "assessment",
      test_completed: true,
      assessment_completed: true,
      score
    });
  }

  async function selectResourcePanel(panel: LessonResourcePanel) {
    setActiveResourcePanel(panel);
    if (!result?.lesson_state) {
      return;
    }
    if (panel === "document" && !lessonState?.notes_completed) {
      await persistLessonState({ current_stage: "artifacts", notes_completed: true });
      await recordLessonProfileEvent({
        action: "document_viewed",
        payload: {
          resource_id: documentResource?.id || "",
          citation_chunk_ids: documentResource?.citation_chunk_ids || []
        }
      });
    }
    if (panel === "mind_map" && !lessonState?.mind_map_completed) {
      await persistLessonState({ current_stage: "artifacts", mind_map_completed: true });
      await recordLessonProfileEvent({
        action: "mind_map_interacted",
        payload: {
          resource_id: mindMapResource?.id || "",
          graph_constraint_count: [
            graphConstraints?.current_node,
            graphConstraints?.parent,
            ...(graphConstraints?.predecessors || []),
            ...(graphConstraints?.successors || [])
          ].filter(Boolean).length
        }
      });
    }
  }

  useEffect(() => {
    const classroom = result?.openmaic_classroom;
    const status = (classroom?.status || "").toLowerCase();
    const hasTerminalError = Boolean(classroom?.error) && ["failed", "error"].includes(status);
    const hasCompletedClassroom = Boolean(classroom?.url || classroom?.classroom_id || ["succeeded", "completed"].includes(status));
    if (!classroom || hasCompletedClassroom || hasTerminalError) {
      setOpenmaicPolling(false);
      setOpenmaicPollError("");
      return;
    }
    if (!classroom.job_id && !classroom.poll_url) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;
    let attempts = 0;
    const maxAttempts = 360;
    const jobId = classroom.job_id;
    const pollUrl = classroom.poll_url;
    const intervalMs = Math.max(3000, Math.min(classroom.poll_interval_ms || 5000, 15000));

    async function poll() {
      if (cancelled) {
        return;
      }
      attempts += 1;
      setOpenmaicPolling(true);
      try {
        const nextClassroom = await pollOpenMAICClassroom(token, jobId, pollUrl);
        if (cancelled) {
          return;
        }
        setResult((current) => current ? {
          ...current,
          openmaic_classroom: {
            ...current.openmaic_classroom,
            ...nextClassroom,
            requirement: current.openmaic_classroom?.requirement || nextClassroom.requirement
          }
        } : current);
        setOpenmaicPollError("");
        const status = nextClassroom.status.toLowerCase();
        if (nextClassroom.url || nextClassroom.classroom_id || ["succeeded", "completed", "failed", "error"].includes(status)) {
          setOpenmaicPolling(false);
          void updateLessonState(token, {
            course_id: numericCourseId,
            node_id: decodedNodeId,
            openmaic_classroom: {
              ...nextClassroom,
              requirement: result?.openmaic_classroom?.requirement || nextClassroom.requirement
            }
          }).catch(() => undefined);
          return;
        }
      } catch (caught) {
        if (!cancelled) {
          setOpenmaicPollError(caught instanceof Error ? caught.message : "查询 OpenMAIC 任务失败");
        }
      }
      if (!cancelled && attempts < maxAttempts) {
        timer = window.setTimeout(poll, intervalMs);
      } else if (!cancelled) {
        setOpenmaicPolling(false);
      }
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [
    result?.openmaic_classroom?.job_id,
    result?.openmaic_classroom?.poll_url,
    result?.openmaic_classroom?.url,
    result?.openmaic_classroom?.classroom_id,
    result?.openmaic_classroom?.error,
    result?.openmaic_classroom?.status,
    token
  ]);

  if (bootLoading) {
    return <div className="route-loading">正在进入知识点学习页</div>;
  }

  return (
    <div className={`page-stack knowledge-learning-workbench ${viewMode === "assess" ? "assessment-mode" : ""}`}>
      <div className="page-heading with-actions product-page-heading">
        <div>
          <span>{viewMode === "learn" ? "Knowledge Point Learning" : "Learning Assessment"}</span>
              <h2>{topic} · {viewMode === "learn" ? "知识点学习" : "学习评估"}</h2>
          <p>
            {viewMode === "learn"
              ? "从学习路径地图点击关卡进入；后端先用 Agentic RAG 与知识图谱生成课堂大纲，再交给 OpenMAIC 前端呈现互动课堂。"
              : "学习完毕后进入评估；通过则解锁下一关，未通过则触发补救路径并动态调整学习规划。"}
          </p>
        </div>
        <div className="header-actions">
          <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${numericCourseId}/learning-path`)}>
            <ArrowLeft size={16} />
            返回学习路径
          </button>
          <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${numericCourseId}/graph`)}>
            <Route size={16} />
            返回图谱
          </button>
          {viewMode === "learn" ? (
            <button className="primary-action compact-button" disabled={loading} onClick={() => generate({ forceRegenerate: true })}>
              {loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
              {loading ? "生成中" : "重新生成"}
            </button>
          ) : (
            <button className="primary-action compact-button" onClick={() => setViewMode("learn")}>
              <FileText size={16} />
              回到学习页
            </button>
          )}
        </div>
      </div>

      {error ? <div className="error">{error}</div> : null}

      {viewMode === "learn" ? (
        <div className="immersive-lesson-shell">
          <section className="lesson-topbar">
            <button className="icon-text-button" onClick={() => navigate(`/courses/${numericCourseId}/learning-path`)} type="button">
              <ArrowLeft size={18} />
              <span>当前场景</span>
            </button>
            <div>
              <span>{course?.name || "课程课堂"}</span>
              <h2>{topic}</h2>
            </div>
            <div className="lesson-topbar-actions">
              <span>{result?.from_cache ? "已保存课堂" : loading ? "生成课堂中" : lessonStageLabel(lessonState)}</span>
              <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${numericCourseId}/graph`)} type="button">
                <Route size={16} />
                图谱
              </button>
            </div>
          </section>

          <section className="lesson-stage-card lesson-classroom-frame-wrap" ref={classroomFrameWrapRef}>
            <div className="lesson-scene-number">{String(sceneIndex).padStart(2, "0")}</div>
            {openmaicUrl ? (
              <>
                <iframe
                  allow={openmaicClassroomIframeAllow}
                  allowFullScreen
                  className="lesson-classroom-frame"
                  src={openmaicUrl}
                  title={`${topic} OpenMAIC 课堂`}
                />
                <div className="lesson-classroom-floating-actions">
                  <button className="secondary-action compact-button" onClick={() => void requestClassroomFullscreen()} type="button">
                    <Maximize2 size={15} />
                    全屏播放
                  </button>
                  <button
                    className="primary-action compact-button"
                    disabled={statusSaving}
                    onClick={() => void completeClassroom()}
                    type="button"
                  >
                    <ListChecks size={15} />
                    {statusSaving ? "保存中" : "进入课堂测试"}
                  </button>
                </div>
              </>
            ) : (
              <div className="lesson-classroom-empty">
                <Bot size={34} />
                <strong>{loading || openmaicPolling ? "正在生成标准课堂" : openmaicHasTerminalError ? "课堂生成失败" : "等待进入课堂"}</strong>
                <p>
                  {loading
                    ? "Agentic RAG 正在检索本地知识库，DeepSeek 生成课堂大纲后会提交到 OpenMAIC。"
                    : openmaicPolling
                      ? "OpenMAIC 已接收任务，正在生成课堂视频和互动场景。"
                      : openmaicHasTerminalError
                        ? openmaicClassroom?.error || "OpenMAIC 课堂生成失败，请点击右上角重新生成。"
                        : "课堂生成完成后将保存在数据库中，再次进入不会重新调用大模型。"}
                </p>
              </div>
            )}
          </section>

          <section className="lesson-control-bar">
            <div className="scene-counter">课堂资源</div>
            {lessonResourcePanels.map((panel) => {
              const Icon = resourceIcons[panel.type];
              const completed =
                panel.key === "document" ? lessonState?.notes_completed :
                panel.key === "mind_map" ? lessonState?.mind_map_completed :
                lessonState?.code_lab_completed;
              return (
                <button
                  className={`lesson-resource-switch ${activeResourcePanel === panel.key ? "active" : ""}`}
                  key={panel.key}
                  onClick={() => void selectResourcePanel(panel.key)}
                  type="button"
                >
                  <Icon size={16} />
                  <span>{panel.label}</span>
                  {completed ? <small>已完成</small> : <small>{panel.detail}</small>}
                </button>
              );
            })}
          </section>

          <section className="lesson-resource-workspace">
            <LessonResourceWorkspace
              activePanel={activeResourcePanel}
              codeLabResource={codeLabResource}
              course={course}
              documentResource={documentResource}
              graphConstraints={graphConstraints}
              knowledgeContext={knowledgeContext}
              mindMapResource={mindMapResource}
              token={token}
              onCodePassed={() => {
                if (result?.lesson_state) {
                  void persistLessonState({ current_stage: "artifacts", code_lab_completed: true });
                }
              }}
              onCodeRun={(event) => {
                void recordLessonProfileEvent({
                  action: event.passed ? "code_attempt_passed" : "code_attempt_run",
                  payload: {
                    actual_output: event.output,
                    attempts: event.attempts,
                    code: event.code,
                    passed: event.passed,
                    resource_id: codeLabResource?.id || ""
                  },
                  score: event.passed ? 1 : 0
                });
              }}
              topic={topic}
            />
          </section>

          <section className="lesson-bottom-dock">
            <aside className="teacher-rail">
              <div className="teacher-avatar">林</div>
              <span>林老师</span>
            </aside>
            <article className="teacher-dialogue">
              <div>
                <strong>林老师</strong>
                <p>
                  {documentResource?.content
                    ? documentResource.content.replace(/[#*_`>-]/g, "").replace(/\s+/g, " ").slice(0, 140)
                    : `${topic} 的课堂内容已按你的画像生成。完成视频课堂后，系统会进入课堂测试，测试完成即代表评估完成。`}
                </p>
              </div>
              <button aria-label="播放讲解" className="icon-action" type="button">
                <PlayCircle size={17} />
              </button>
            </article>
            <div className="lesson-dock-actions">
              <button
                className="primary-action compact-button"
                disabled={!postClassroomUnlocked || statusSaving}
                onClick={completeClassroom}
                type="button"
              >
                <ListChecks size={16} />
                {statusSaving ? "保存中" : "课堂结束，进入测试"}
              </button>
            </div>
          </section>

          <section className="lesson-insight-grid">
            <AgentTheater pkg={result} requestedTypes={resourceTypes} running={loading} />
            <AgentCollaborationPanel pkg={result} requestedTypes={resourceTypes} running={loading} />
            <section className="panel rag-guardrail-panel">
              <div className="panel-title">
                <ShieldAlert size={18} />
                <h2>协同闭环裁决</h2>
                <span>{decisionReport?.decision === "accepted" ? "已通过" : "待决策"}</span>
              </div>
              <div className="closed-loop-steps">
                <span className={analysisPlan ? "done" : ""}>分析</span>
                <span className={knowledgeContext.length ? "done" : ""}>检索</span>
                <span className={resources.length ? "done" : ""}>生成</span>
                <span className={verificationReport ? "done" : ""}>校验</span>
                <span className={debateReport ? "done" : ""}>辩论</span>
                <span className={decisionReport ? "done" : ""}>决策</span>
              </div>
              <div className="decision-card">
                <strong>{decisionReport?.decision || "pending"}</strong>
                <p>{decisionReport?.reason || "等待多智能体完成交叉验证和裁决。"}</p>
              </div>
            </section>
            <section className="panel knowledge-source-panel">
              <div className="panel-title">
                <GitBranch size={18} />
                <h2>MySQL 原文依据</h2>
              </div>
              <div className="knowledge-source-list">
                {knowledgeContext.length ? knowledgeContext.slice(0, 3).map((item) => (
                  <article key={`${item.chunk_id}-${item.source_locator}`}>
                    <strong>{item.source_locator} · chunk #{item.chunk_id}</strong>
                    <p>{item.content}</p>
                  </article>
                )) : <p className="empty">等待后端检索课程知识库 chunks。</p>}
              </div>
            </section>
          </section>
        </div>
      ) : (
        <div className="immersive-lesson-shell test-mode">
          <section className="lesson-topbar">
            <button className="icon-text-button" onClick={() => setViewMode("learn")} type="button">
              <ArrowLeft size={18} />
              <span>返回课堂</span>
            </button>
            <div>
              <span>当前场景</span>
              <h2>{lessonState?.assessment_completed ? "课堂测试已完成" : "课堂测试"}</h2>
            </div>
            <div className="lesson-topbar-actions">
              <span>{lessonStageLabel(lessonState)}</span>
            </div>
          </section>

          <section
            className="lesson-stage-card quiz-stage-card"
            onClick={focusAssessmentPanel}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                focusAssessmentPanel();
              }
            }}
            role="button"
            tabIndex={0}
          >
            <div className="panel-title">
              <Activity size={18} />
              <h2>基础语法小测验</h2>
              <span>3 道题 · 共 100 分</span>
            </div>
            <div className="quiz-hero">
              <div className="quiz-icon"><Activity size={28} /></div>
              <strong>随堂测验</strong>
              <p>检测你的学习成果。测试完成后即代表本节课评估完成，系统会写回知识图谱掌握状态。</p>
              <div>
                <span>3 道题</span>
                <span>共 100 分</span>
              </div>
            </div>
          </section>

          <section className="lesson-test-layout" id="lesson-assessment-panel">
            <AssessmentPanel
              courseId={numericCourseId}
              exerciseResource={exerciseResource}
              hasResult={Boolean(result)}
              lessonState={lessonState}
              nodeId={textValue(node, "id", decodedNodeId)}
              onCodePassed={() => {
                if (result?.lesson_state) {
                  void persistLessonState({ current_stage: "test", code_lab_completed: true });
                }
              }}
              onSubmitted={async (report, score) => {
                await completeAssessment(score);
                setAssessmentScoreSeed(score);
                const targetNodeId = encodeURIComponent(textValue(node, "id", decodedNodeId));
                if (report.passed === false || score < assessmentThreshold) {
                  navigate(`/courses/${numericCourseId}/learning-path?mode=remedial&focus=${targetNodeId}`);
                  return;
                }
                navigate(`/courses/${numericCourseId}/learning-path`);
              }}
              initialScore={assessmentScoreSeed}
              studentId={profile?.student_id}
              token={token}
              courseName={course?.name}
              topic={topic}
            />
            <section className="panel assessment-branch-panel">
              <div className="panel-title">
                <ShieldAlert size={18} />
                <h2>路径分支</h2>
              </div>
              <div className="branch-card fail">
                <strong>未达标</strong>
                <p>进入补救路径，围绕失败知识点和前置依赖重新规划。</p>
              </div>
              <div className="branch-card pass">
                <strong>达标</strong>
                <p>回到主线地图，继续下一个知识点学习。</p>
              </div>
              <div className="threshold-row">
                <Clock3 size={15} />
                <span>通过阈值 {Math.round(assessmentThreshold * 100)} 分</span>
              </div>
            </section>
          </section>
        </div>
      )}
    </div>
  );
}

function LessonResourceWorkspace({
  activePanel,
  codeLabResource,
  course,
  documentResource,
  graphConstraints,
  knowledgeContext,
  mindMapResource,
  onCodePassed,
  onCodeRun,
  token,
  topic
}: {
  activePanel: LessonResourcePanel;
  codeLabResource?: Resource;
  course?: Course;
  documentResource?: Resource;
  graphConstraints?: GraphConstraints;
  knowledgeContext: KnowledgeContextItem[];
  mindMapResource?: Resource;
  onCodePassed: () => void;
  onCodeRun: (event: InlineCodeRunEvent) => void;
  token?: string;
  topic: string;
}) {
  if (activePanel === "document") {
    return (
      <div className="lesson-resource-grid document-view">
        <section className="panel lesson-resource-primary">
          <div className="panel-title">
            <FileText size={18} />
            <h2>该节课文档</h2>
            <span>Document Agent</span>
          </div>
          {documentResource ? <ResourceCard resource={documentResource} /> : <p className="empty">文档 Agent 还没有返回内容。</p>}
        </section>
        <LessonEvidencePanel knowledgeContext={knowledgeContext} />
      </div>
    );
  }

  if (activePanel === "mind_map") {
    return (
      <div className="lesson-resource-grid map-view">
        <section className="panel lesson-resource-primary">
          <div className="panel-title">
            <GitBranch size={18} />
            <h2>这节课知识点的思维导图</h2>
            <span>MindMap Agent</span>
          </div>
          {mindMapResource ? (
            <MindMapViewer
              graphConstraints={graphConstraints}
              knowledgeContext={knowledgeContext}
              resource={mindMapResource}
              topic={topic}
            />
          ) : <p className="empty">思维导图 Agent 还没有返回内容。</p>}
        </section>
        <section className="panel graph-constraint-panel">
          <div className="panel-title">
            <Route size={18} />
            <h2>图谱逻辑约束</h2>
          </div>
          <div className="graph-constraint-list">
            <span>当前节点：{graphConstraints?.current_node?.name || topic}</span>
            <span>父章节：{graphConstraints?.parent?.name || "暂无"}</span>
            <span>前置依赖：{graphConstraints?.predecessors?.map((item) => item.name).join("、") || "无"}</span>
            <span>后继知识：{graphConstraints?.successors?.map((item) => item.name).join("、") || "无"}</span>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="lesson-resource-grid code-view">
      <section className="panel lesson-resource-primary">
        <div className="panel-title">
          <Code2 size={18} />
          <h2>编程练习</h2>
          <span>CodeLab Agent</span>
        </div>
        <InlineLessonCodeLab
          course={course}
          codeLabResource={codeLabResource}
          onCodePassed={onCodePassed}
          onCodeRun={onCodeRun}
          token={token}
          topic={topic}
        />
      </section>
      <LessonEvidencePanel knowledgeContext={knowledgeContext} />
    </div>
  );
}

interface InlineCodeRunEvent {
  attempts: number;
  code: string;
  output: string;
  passed: boolean;
  serverVerdict?: string | null;
}

function LessonEvidencePanel({ knowledgeContext }: { knowledgeContext: KnowledgeContextItem[] }) {
  return (
    <section className="panel lesson-evidence-panel">
      <div className="panel-title">
        <ShieldAlert size={18} />
        <h2>生成依据</h2>
        <span>MySQL chunks</span>
      </div>
      <div className="knowledge-source-list">
        {knowledgeContext.length ? knowledgeContext.slice(0, 4).map((item) => (
          <article key={`${item.chunk_id}-${item.source_locator}`}>
            <strong>{item.source_locator} · chunk #{item.chunk_id}</strong>
            <p>{item.content}</p>
          </article>
        )) : <p className="empty">暂无检索证据。</p>}
      </div>
    </section>
  );
}

function InlineLessonCodeLab({
  codeLabResource,
  course,
  onCodePassed,
  onCodeRun,
  token,
  topic
}: {
  codeLabResource?: Resource;
  course?: Course;
  onCodePassed: () => void;
  onCodeRun: (event: InlineCodeRunEvent) => void;
  token?: string;
  topic: string;
}) {
  const codeLabModel = useMemo(
    () => lessonCodeLabViewModel({ course, resource: codeLabResource, topic }),
    [codeLabResource, course, topic]
  );
  const starter = codeLabModel.starterCode;
  const [code, setCode] = useState(starter);
  const [output, setOutput] = useState("点击运行，代码将提交服务端沙箱真实编译执行。");
  const [passed, setPassed] = useState(false);
  const [attempts, setAttempts] = useState(0);
  const [running, setRunning] = useState(false);
  const [serverVerdict, setServerVerdict] = useState<string | null>(null);
  const [runSnapshot, setRunSnapshot] = useState<{ verdict: string; stderr: string; compile_output: string; stdout: string } | null>(null);

  useEffect(() => {
    setCode(starter);
    setOutput("点击运行，代码将提交服务端沙箱真实编译执行。");
    setPassed(false);
    setAttempts(0);
  }, [starter]);

  async function runCode() {
    if (running) {
      return;
    }
    setRunning(true);
    const nextAttempts = attempts + 1;
    setAttempts(nextAttempts);
    try {
      const outcome = await executeCode({
        token,
        courseId: course?.id,
        source: code,
        expectedOutput: ""
      });
      const nextOutput = outcome.output;
      setOutput(nextOutput);
      setServerVerdict(outcome.verdict);
      setRunSnapshot(
        outcome.serverVerified
          ? { verdict: outcome.verdict || "", stderr: outcome.output, compile_output: "", stdout: outcome.output }
          : null
      );
      const ok = outcome.serverVerified ? Boolean(outcome.passed) : isInlineCodeRunSuccessful(nextOutput);
      setPassed(ok);
      if (!ok) {
        // 双信号融合（issue #15）：代码失败广播给状态感知，困惑×连续失败触发高置信介入
        window.dispatchEvent(
          new CustomEvent(CODE_RUN_FAILED_EVENT, {
            detail: { summary: outcome.message || outcome.output?.slice(0, 80) || "代码运行失败" }
          })
        );
      }
      onCodeRun({ attempts: nextAttempts, code, output: nextOutput, passed: ok, serverVerdict: outcome.verdict });
      if (ok) {
        onCodePassed();
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="lesson-code-lab-pro">
      <article className="code-lab-brief">
        <strong>{codeLabResource?.title || `${topic} 编程练习`}</strong>
        <p>
          {codeLabResource?.recommendation_reason ||
            "根据本地知识库证据与学生画像生成短代码练习，要求能运行、能解释输出、能迁移到相近知识点。"}
        </p>
      </article>
      <div className="inline-code-lab">
        <div className="code-editor-shell">
          <div className="code-toolbar">
            <span>{codeLabModel.labLabel}</span>
            <div>
              <button className="secondary-action compact-button" onClick={() => setCode(starter)} type="button">
                <RefreshCw size={15} />
                重置
              </button>
              <button className="primary-action compact-button" disabled={running} onClick={runCode} type="button">
                <PlayCircle size={15} />
                {running ? "沙箱运行中…" : "运行代码"}
              </button>
            </div>
          </div>
          <textarea aria-label="在线编程练习编辑器" onChange={(event) => setCode(event.target.value)} value={code} />
        </div>
        <div className="code-output-panel">
          <span>
            真实运行结果
            {serverVerdict ? (
              <em className={`sandbox-badge ${serverVerdict === "accepted" ? "ok" : "warn"}`}>
                服务端沙箱 · {serverVerdict === "accepted" ? "运行通过" : serverVerdict === "wrong_answer" ? "输出不一致" : serverVerdict === "compile_error" ? "编译失败" : serverVerdict === "timeout" ? "运行超时" : "运行出错"}
              </em>
            ) : null}
          </span>
          <pre>{output}</pre>
          {passed ? <p className="auto-advance-note">服务端沙箱真实运行通过，已记录为本节课代码实践完成。</p> : null}
        </div>
        {runSnapshot && runSnapshot.verdict !== "accepted" ? (
          <DebugMentorPanel
            courseId={course?.id || 0}
            nodeId=""
            topic={topic}
            sourceCode={code}
            runResult={runSnapshot}
            token={token}
            onApplyFix={(fixedCode) => {
              if (fixedCode) {
                setCode(fixedCode);
                window.setTimeout(() => { void runCode(); }, 300);
              }
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

