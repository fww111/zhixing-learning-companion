import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  Flag,
  Loader2,
  Lock,
  Play,
  RefreshCw,
  Route,
  ShieldAlert,
} from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  planCourseLearningPath,
  type CourseLearningPath,
  type CourseLearningStage,
  type ResourceType
} from "../api/client";
import { useAuth } from "../state/auth";
import { canOpenLearningPathStage, chapterSwitchSearchParams, cleanChapterTitle, learningTargetNodeId } from "./learningPathStageModel";

const masteryLabels: Record<string, string> = {
  not_started: "未学习",
  severe_weak: "严重弱项",
  basic: "掌握基础",
  good: "达标良好",
  proficient: "精通"
};

const resourceLabels: Record<ResourceType, string> = {
  document: "讲解文档",
  mind_map: "思维导图",
  exercise: "分层练习",
  reading: "拓展阅读",
  video: "视频脚本",
  code_lab: "代码实操"
};

const pathStatusLabels: Record<string, string> = {
  current: "当前关卡",
  passed: "已通过",
  locked: "待解锁",
  open: "待学习"
};

function masteryText(status: string): string {
  return masteryLabels[status] || status || "未学习";
}

function pathStatusText(status: string): string {
  return pathStatusLabels[status] || status || "待学习";
}

function resourceText(type: string): string {
  return resourceLabels[type as ResourceType] || type;
}

function stageScheduleText(stage: CourseLearningStage): string {
  const minutes = stage.scheduled_minutes || stage.estimated_minutes;
  if (stage.is_today_task) {
    return `今日任务 · ${minutes} 分钟`;
  }
  if (stage.scheduled_day) {
    const dateText = stage.scheduled_date ? `${stage.scheduled_date} ` : "";
    return `${dateText}${stage.schedule_label || `${stage.scheduled_day}任务`} · ${minutes} 分钟`;
  }
  return `${stage.schedule_label || "后续任务"} · 约 ${stage.estimated_minutes} 分钟`;
}

function pathIcon(stage: CourseLearningStage) {
  if (stage.is_current) {
    return <Play size={18} />;
  }
  if (stage.path_status === "passed") {
    return <CheckCircle2 size={18} />;
  }
  if (stage.path_status === "locked") {
    return <Lock size={18} />;
  }
  return <Flag size={18} />;
}

export function CourseLearningPathPage() {
  const { courseId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { token } = useAuth();
  const numericCourseId = Number(courseId);
  const mode = searchParams.get("mode") === "remedial" ? "remedial" : "main";
  const focusNodeId = searchParams.get("focus") || "";
  const selectedChapterId = searchParams.get("chapter") || "";
  const [path, setPath] = useState<CourseLearningPath>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const stages = path?.stages ?? [];
  const currentStage = stages.find((stage) => stage.node_id === path?.current_stage_id);
  const cleanedActiveChapterTitle = useMemo(
    () => cleanChapterTitle(path?.active_chapter_title || ""),
    [path?.active_chapter_title]
  );

  async function loadPath() {
    if (!Number.isFinite(numericCourseId)) {
      setError("课程 ID 无效");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const nextPath = await planCourseLearningPath(token, numericCourseId, {
        plan_type: mode,
        focus_node_id: focusNodeId,
        chapter_id: selectedChapterId
      });
      setPath(nextPath);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "生成学习路径失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPath();
  }, [numericCourseId, token, mode, focusNodeId, selectedChapterId]);

  function selectChapter(chapterId: string) {
    const nextSearch = chapterSwitchSearchParams(searchParams.toString(), chapterId);
    navigate(`/courses/${numericCourseId}/learning-path${nextSearch ? `?${nextSearch}` : ""}`, { replace: true });
  }

  function openStage(stage: CourseLearningStage) {
    if (!canOpenLearningPathStage(stage)) {
      return;
    }
    const targetNodeId = learningTargetNodeId(stage);
    navigate(`/courses/${numericCourseId}/knowledge/${encodeURIComponent(targetNodeId)}`, {
      state: {
        node: {
          id: targetNodeId,
          name: stage.topic,
          level: stage.level,
          order: stage.order,
          mastery_status: stage.mastery_status,
          mastery_score: stage.mastery_score
        },
        resourceTypes: stage.recommended_resource_types,
        stage
      }
    });
  }

  if (loading && !path) {
    return <div className="route-loading">正在生成动态学习路径</div>;
  }

  return (
    <div className="page-stack learning-path-workbench">
      <div className="page-heading with-actions command-heading product-page-heading">
        <div>
          <span>{mode === "remedial" ? "Remedial Quest" : "Main Quest"}</span>
          <h2>{mode === "remedial" ? "补救支线地图" : "主线任务地图"}</h2>
          <p>
            根据学生画像、知识图谱和掌握度动态规划。今日任务必须当天完成，额外时间可继续学习后续关卡。
          </p>
        </div>
        <div className="header-actions">
          <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${numericCourseId}/graph`)}>
            <ArrowLeft size={16} />
            返回图谱
          </button>
          {mode === "remedial" ? (
            <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${numericCourseId}/learning-path`)}>
              <Route size={16} />
              回到主线
            </button>
          ) : null}
          <button className="primary-action compact-button" disabled={loading} onClick={loadPath}>
            {loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            {loading ? "重算中" : "重新规划"}
          </button>
        </div>
      </div>

      {error ? <div className="error">{error}</div> : null}

      <div className="learning-layout learning-path-map-only">
        <section className="center-column">
          <section className={`panel path-map-panel ${mode === "remedial" ? "remedial" : ""}`}>
            <div className="panel-title path-map-title">
              <div className="path-map-title-main">
                {mode === "remedial" ? <ShieldAlert size={18} /> : <Route size={18} />}
                <h2>{mode === "remedial" ? "补救支线地图" : "主线任务地图"}</h2>
                {currentStage ? <span>当前：{currentStage.topic}</span> : null}
              </div>
              <label className="chapter-select-control">
                <span>章节</span>
                <select
                  aria-label="切换章节"
                  value={path?.active_chapter_id || selectedChapterId}
                  onChange={(event) => selectChapter(event.target.value)}
                >
                  {path?.chapters?.map((chapter) => (
                    <option key={chapter.id} value={chapter.id}>
                      {cleanChapterTitle(chapter.title)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {cleanedActiveChapterTitle ? <p className="path-map-chapter-note">{cleanedActiveChapterTitle}</p> : null}

            <div className="mastery-legend">
              {Object.entries(masteryLabels).map(([status, label]) => (
                <span className={`mastery-dot-label mastery-${status}`} key={status}>
                  <i />
                  {label}
                </span>
              ))}
            </div>

            {stages.length ? (
              <div className="quest-map" aria-label="关卡式学习路径">
                <div className="quest-road" />
                {stages.map((stage, index) => (
                  <article
                    className={[
                      "quest-level",
                      index % 2 === 0 ? "left" : "right",
                      `status-${stage.path_status}`,
                      stage.is_current ? "current" : "",
                      stage.is_remedial ? "remedial" : ""
                    ].filter(Boolean).join(" ")}
                    key={stage.node_id}
                  >
                    <button
                      aria-label={`进入 ${stage.topic}`}
                      className={`quest-node mastery-${stage.mastery_status}`}
                      disabled={!canOpenLearningPathStage(stage)}
                      onClick={() => openStage(stage)}
                      type="button"
                    >
                      <span>{index + 1}</span>
                      {pathIcon(stage)}
                    </button>
                    <div className="quest-card">
                      <div className="quest-card-heading">
                        <span className={`mastery-tag mastery-${stage.mastery_status}`}>
                          {masteryText(stage.mastery_status)}
                        </span>
                        <span className={`path-status-tag status-${stage.path_status}`}>
                          {pathStatusText(stage.path_status)}
                        </span>
                      </div>
                      <button
                        className="quest-title-button"
                        disabled={!canOpenLearningPathStage(stage)}
                        onClick={() => openStage(stage)}
                        type="button"
                      >
                        {stage.topic}
                      </button>
                      <small>
                        L{stage.level} · {stage.estimated_minutes} 分钟 · 优先级 {stage.priority_score.toFixed(0)}
                      </small>
                      <div className={`stage-schedule ${stage.is_today_task ? "today" : ""}`}>
                        <CalendarDays size={14} />
                        <span>{stageScheduleText(stage)}</span>
                      </div>
                      <p>{stage.goal}</p>
                      <div className="stage-meta-row">
                        {stage.recommended_resource_types.slice(0, 4).map((type) => (
                          <span className="resource-chip" key={type}>{resourceText(type)}</span>
                        ))}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="empty">暂无学习路径，请先构建课程知识图谱。</p>
            )}
          </section>
        </section>
      </div>
    </div>
  );
}
