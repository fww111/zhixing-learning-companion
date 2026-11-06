import { ArrowRight, BookOpenCheck, CalendarClock, CheckCircle2, Flame, ListChecks, Loader2, MapPinned, PlayCircle, RefreshCw, Target } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getCourse,
  getKnowledgeGraph,
  listLearningProfileEvents,
  planCourseLearningPath,
  type Course,
  type KnowledgeGraph,
  type LearningProfileEvent
} from "../api/client";
import { useAuth } from "../state/auth";
import { buildTodayDashboardModel, type MasteryStats, type TodayDashboardModel } from "./todayDashboardModel";

const WEEKDAY_LABELS = ["日", "一", "二", "三", "四", "五", "六"];

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) {
    return "夜深了，注意休息";
  }
  if (hour < 12) {
    return "早上好";
  }
  if (hour < 18) {
    return "下午好";
  }
  return "晚上好";
}

export function TodayPage() {
  const { courseId } = useParams();
  const navigate = useNavigate();
  const { token } = useAuth();
  const numericCourseId = Number(courseId);
  const [course, setCourse] = useState<Course>();
  const [model, setModel] = useState<TodayDashboardModel>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    if (!Number.isFinite(numericCourseId)) {
      setError("课程 ID 无效");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [nextCourse, nextPath, nextGraph, nextEvents] = await Promise.all([
        getCourse(token, numericCourseId),
        planCourseLearningPath(token, numericCourseId).catch(() => undefined),
        getKnowledgeGraph(token, numericCourseId).catch(() => undefined),
        listLearningProfileEvents(token, numericCourseId).catch(() => [] as LearningProfileEvent[])
      ]);
      setCourse(nextCourse);
      setModel(
        buildTodayDashboardModel({
          path: nextPath,
          graph: nextGraph,
          events: nextEvents,
          today: new Date().toISOString().slice(0, 10)
        })
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载今日学习失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numericCourseId, token]);

  const dateLabel = useMemo(() => {
    const now = new Date();
    return `${now.getMonth() + 1} 月 ${now.getDate()} 日 · 星期${WEEKDAY_LABELS[now.getDay()]}`;
  }, []);

  if (loading && !model) {
    return (
      <div className="today-page">
        <div className="route-loading">
          <Loader2 className="spin" size={20} />
          <span>正在为你准备今天的学习计划…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-stack today-page">
      <section className="today-hero">
        <div>
          <p className="today-hero-date">{dateLabel}</p>
          <h2>
            {greeting()}，继续「{course?.name || "当前课程"}」吧
          </h2>
          <p className="today-hero-sub">
            {model?.streak.days
              ? `已连续学习 ${model.streak.days} 天，保持下去。`
              : "从今日任务开始，学一点就是进步。"}
          </p>
        </div>
        <div className="today-hero-actions">
          <button className="secondary-action compact-button" onClick={load} type="button">
            <RefreshCw className={loading ? "spin" : ""} size={15} />
            刷新
          </button>
        </div>
      </section>

      {error ? <div className="error">{error}</div> : null}

      {model ? (
        <>
          <div className="today-grid">
            <section className="panel today-task-card">
              <div className="today-card-head">
                <Target size={17} />
                <h3>今日任务</h3>
                {model.pathScheduleSummary ? <span className="today-chip">{model.pathScheduleSummary}</span> : null}
              </div>
              {model.todayTasks.length ? (
                <ul className="today-task-list">
                  {model.todayTasks.slice(0, 3).map((task) => (
                    <li key={task.node_id}>
                      <div className="today-task-info">
                        <strong>{task.topic}</strong>
                        <small>
                          <CalendarClock size={12} />
                          约 {task.scheduled_minutes || task.estimated_minutes} 分钟
                          {task.is_remedial ? " · 薄弱补救" : ""}
                        </small>
                        {task.goal ? <em>{task.goal}</em> : null}
                      </div>
                      <button
                        className="primary-action compact-button"
                        onClick={() => navigate(`/courses/${numericCourseId}/knowledge/${encodeURIComponent(task.node_id)}`)}
                        type="button"
                      >
                        <PlayCircle size={14} />
                        开始学习
                      </button>
                    </li>
                  ))}
                </ul>
              ) : model.hasPath ? (
                <div className="today-empty-task">
                  <CheckCircle2 size={18} />
                  <span>今日任务已完成，可以继续后续关卡。</span>
                </div>
              ) : (
                <div className="today-empty-task">
                  <MapPinned size={18} />
                  <span>还没有学习路径，去生成你的专属计划。</span>
                  <button
                    className="secondary-action compact-button"
                    onClick={() => navigate(`/courses/${numericCourseId}/learning-path`)}
                    type="button"
                  >
                    生成路径
                    <ArrowRight size={14} />
                  </button>
                </div>
              )}
              {model.upcomingTasks.length ? (
                <div className="today-upcoming">
                  <span>接下来</span>
                  <div className="today-upcoming-list">
                    {model.upcomingTasks.map((task) => (
                      <button
                        key={task.node_id}
                        onClick={() => navigate(`/courses/${numericCourseId}/knowledge/${encodeURIComponent(task.node_id)}`)}
                        type="button"
                      >
                        {task.topic}
                        <ArrowRight size={12} />
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>

            <div className="today-metric-col">
              <MasteryCard navigate={navigate} courseId={numericCourseId} stats={model.mastery} />
              <button className="panel today-metric-card clickable" onClick={() => navigate(`/courses/${numericCourseId}/assessment/wrong-questions`)} type="button">
                <ListChecks size={18} />
                <strong>{model.wrongQuestionCount}</strong>
                <span>待重做错题</span>
                <small>{model.resolvedWrongCount} 题已修正</small>
              </button>
              <button className="panel today-metric-card clickable" onClick={() => navigate(`/courses/${numericCourseId}/tutor-stage`)} type="button">
                <Flame size={18} />
                <strong>{model.weekEventCount}</strong>
                <span>本周学习记录</span>
                <small>想提问？进 AI 对话大屏</small>
              </button>
            </div>
          </div>

          {model.recentTopics.length ? (
            <section className="panel today-recent">
              <div className="today-card-head">
                <BookOpenCheck size={16} />
                <h3>最近在学</h3>
              </div>
              <div className="today-topic-list">
                {model.recentTopics.map((topic) => (
                  <span key={topic}>{topic}</span>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function MasteryCard({
  courseId,
  navigate,
  stats
}: {
  courseId: number;
  navigate: (to: string) => void;
  stats: MasteryStats;
}) {
  const distribution: Array<{ key: keyof MasteryStats; label: string; className: string }> = [
    { key: "notStarted", label: "未学习", className: "mastery-unlearned" },
    { key: "severeWeak", label: "严重弱项", className: "mastery-weak" },
    { key: "basic", label: "掌握基础", className: "mastery-basic" },
    { key: "good", label: "达标良好", className: "mastery-good" },
    { key: "proficient", label: "精通", className: "mastery-proficient" }
  ];
  return (
    <button
      className="panel today-metric-card clickable"
      onClick={() => navigate(`/courses/${courseId}/graph`)}
      type="button"
    >
      <Target size={18} />
      <strong>{stats.masteredPercent}%</strong>
      <span>知识点掌握度</span>
      <div className="today-mastery-bar" aria-hidden="true">
        {distribution.map((item) => {
          const value = stats[item.key];
          const percent = stats.total ? (Number(value) / stats.total) * 100 : 0;
          return <span key={item.label} className={item.className} style={{ width: `${percent}%` }} title={`${item.label} ${value}`} />;
        })}
      </div>
      <small>
        {stats.weakFocusCount ? `${stats.weakFocusCount} 个薄弱点待补` : "暂无严重弱项"}
      </small>
    </button>
  );
}
