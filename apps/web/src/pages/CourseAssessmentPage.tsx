import { Activity, ArrowLeft, ArrowRight, BarChart3, BookOpenCheck, CheckCircle2, Code2, ListChecks, Network, RefreshCw, Route, ShieldAlert, Target } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getCourse,
  getKnowledgeGraph,
  listLearningProfileEvents,
  type Course,
  type KnowledgeGraph,
  type LearningProfileEvent
} from "../api/client";
import { useAuth } from "../state/auth";
import {
  buildCourseAssessmentDashboardModel,
  type AssessmentDimensionCard
} from "./courseAssessmentDashboardModel";
import { buildWrongQuestionBookModel } from "./courseWrongQuestionBookModel";
import { buildAssessmentTrend } from "./courseAssessmentDashboardModel";
import { MasteryDistributionChart, MasteryRadarChart, ScoreTrendChart, type MasterySlice } from "../components/MasteryCharts";

const masteryLabels: Record<string, string> = {
  not_started: "未学习",
  severe_weak: "严重弱项",
  basic: "掌握基础",
  good: "达标良好",
  proficient: "精通"
};

const dimensionIcons: Record<string, typeof Activity> = {
  classroom: BookOpenCheck,
  quiz: ListChecks,
  code: Code2,
  behavior: Activity,
  mastery: Target,
  remedial: ShieldAlert,
  coverage: BarChart3
};

export function CourseAssessmentPage() {
  const { courseId } = useParams();
  const navigate = useNavigate();
  const { token } = useAuth();
  const numericCourseId = Number(courseId);
  const [course, setCourse] = useState<Course>();
  const [graph, setGraph] = useState<KnowledgeGraph>();
  const [events, setEvents] = useState<LearningProfileEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const dashboard = useMemo(
    () => buildCourseAssessmentDashboardModel({ events, nodes: graph?.nodes ?? [] }),
    [events, graph]
  );
  const wrongBook = useMemo(
    () => buildWrongQuestionBookModel({ events, nodes: graph?.nodes ?? [] }),
    [events, graph]
  );
  const trendPoints = useMemo(() => buildAssessmentTrend(events), [events]);
  const masterySlices = useMemo<MasterySlice[]>(() => [
    { key: "not_started", label: "未学习", value: dashboard.masteryCounts["not_started"] ?? 0, color: "#94a3b8" },
    { key: "severe_weak", label: "严重弱项", value: dashboard.masteryCounts["severe_weak"] ?? 0, color: "#ef4444" },
    { key: "basic", label: "掌握基础", value: dashboard.masteryCounts["basic"] ?? 0, color: "#f59e0b" },
    { key: "good", label: "达标良好", value: dashboard.masteryCounts["good"] ?? 0, color: "#84cc16" },
    { key: "proficient", label: "精通", value: dashboard.masteryCounts["proficient"] ?? 0, color: "#16a34a" }
  ], [dashboard.masteryCounts]);

  async function load() {
    if (!Number.isFinite(numericCourseId)) {
      setError("课程 ID 无效");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [nextCourse, nextGraph] = await Promise.all([
        getCourse(token, numericCourseId),
        getKnowledgeGraph(token, numericCourseId)
      ]);
      const nextEvents = await listLearningProfileEvents(token, numericCourseId).catch(() => []);
      setCourse(nextCourse);
      setGraph(nextGraph);
      setEvents(nextEvents);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载学习评估失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [numericCourseId, token]);

  return (
    <div className="page-stack course-assessment-workbench">
      <div className="page-heading with-actions product-page-heading">
        <div>
          <span>Learning Assessment</span>
          <h2>{course?.name || "课程"} · 学习评估总览</h2>
          <p>
            学习评估不是学习路径按钮的别名。它汇总知识点测试结果、图谱颜色状态和下一轮动态规划入口；单个知识点的测试仍从学习页闭环进入。
          </p>
        </div>
        <div className="header-actions">
          <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${numericCourseId}/learning-path`)}>
            <ArrowLeft size={16} />
            学习路径
          </button>
          <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${numericCourseId}/graph`)}>
            <Network size={16} />
            知识图谱
          </button>
          <button className="primary-action compact-button" disabled={loading} onClick={load}>
            <RefreshCw className={loading ? "spin" : ""} size={16} />
            {loading ? "刷新中" : "刷新评估"}
          </button>
        </div>
      </div>

      {error ? <div className="error">{error}</div> : null}

      <section className="assessment-overview-grid">
        <article className="panel metric-panel">
          <Activity size={20} />
          <strong>{dashboard.summary.assessedNodes}/{dashboard.summary.totalLearningNodes || 0}</strong>
          <span>已评估知识点</span>
        </article>
        <article className="panel metric-panel">
          <CheckCircle2 size={20} />
          <strong>{dashboard.summary.passedNodes}</strong>
          <span>达标或精通知识点</span>
        </article>
        <article className="panel metric-panel">
          <ShieldAlert size={20} />
          <strong>{dashboard.summary.weakNodes}</strong>
          <span>需要补救的知识点</span>
        </article>
        <article className="panel metric-panel">
          <Route size={20} />
          <strong>{dashboard.summary.latestScore ? `${dashboard.summary.latestScore}%` : "-"}</strong>
          <span>{dashboard.summary.latestScore ? "最近综合得分" : "等待评估提交"}</span>
        </article>
      </section>

      <div className="assessment-dashboard-layout">
        <section className="center-column">
          <section className="panel assessment-visual-panel">
            <div className="panel-title">
              <Target size={18} />
              <h2>多维评估画像</h2>
              <span>课堂 · 题库 · 编程 · 行为 · 图谱</span>
            </div>
            <MasteryRadarChart cards={dashboard.dimensionCards} />
            <div className="assessment-dimension-board">
              {dashboard.dimensionCards.map((card) => <DimensionCard card={card} key={card.key} />)}
            </div>
          </section>

          <section className="panel score-trend-panel">
            <div className="panel-title">
              <Activity size={18} />
              <h2>评估分数趋势</h2>
              <span>每次课堂测试的综合得分</span>
            </div>
            <ScoreTrendChart points={trendPoints} />
          </section>

          <section className="panel mastery-distribution-panel">
            <div className="panel-title">
              <BarChart3 size={18} />
              <h2>知识图谱掌握颜色分布</h2>
            </div>
            <MasteryDistributionChart slices={masterySlices} />
            <div className="assessment-mastery-grid">
              {Object.entries(masteryLabels).map(([status, label]) => (
                <article className={`mastery-distribution-card mastery-${status}`} key={status}>
                  <i />
                  <span>{label}</span>
                  <strong>{dashboard.masteryCounts[status] ?? 0}</strong>
                </article>
              ))}
            </div>
          </section>

          <section className="panel">
            <div className="panel-title">
              <ShieldAlert size={18} />
              <h2>薄弱点补救队列</h2>
            </div>
            <div className="assessment-node-list">
              {dashboard.weakNodeCards.length ? dashboard.weakNodeCards.map((node) => {
                const nodeId = node.id;
                return (
                  <article key={nodeId || node.name}>
                    <div>
                      <span className={`mastery-tag mastery-${node.masteryStatus}`}>{masteryLabels[node.masteryStatus] || node.masteryStatus}</span>
                      <strong>{node.name || nodeId || "知识点"}</strong>
                      <p>{node.summary || "评估未达标，建议进入补救支线并重新生成针对性学习资源。"}</p>
                    </div>
                    <button
                      className="secondary-action compact-button"
                      disabled={!nodeId}
                      onClick={() => navigate(`/courses/${numericCourseId}/learning-path?mode=remedial&focus=${encodeURIComponent(nodeId)}`)}
                      type="button"
                    >
                      补救规划
                    </button>
                  </article>
                );
              }) : <p className="empty">暂无严重弱项或基础掌握节点。完成更多知识点测试后，这里会形成补救队列。</p>}
            </div>
          </section>

          <section className="panel">
            <div className="panel-title">
              <CheckCircle2 size={18} />
              <h2>最近评估记录</h2>
            </div>
            <div className="assessment-node-list compact">
              {dashboard.recentNodeCards.length ? dashboard.recentNodeCards.map((node) => {
                const nodeId = node.id;
                const score = node.masteryScore;
                return (
                  <article key={nodeId || node.name}>
                    <div>
                      <span className={`mastery-tag mastery-${node.masteryStatus}`}>{masteryLabels[node.masteryStatus] || node.masteryStatus}</span>
                      <strong>{node.name || nodeId || "知识点"}</strong>
                      <p>{score === undefined ? "已有评估状态" : `评估得分 ${Math.round(score * 100)}%，图谱颜色已按掌握状态更新。`}</p>
                    </div>
                  </article>
                );
              }) : <p className="empty">尚无知识点评估记录。请从学习路径进入某个知识点完成学习和测试。</p>}
            </div>
          </section>
        </section>

        <aside className="right-column">
          <section className="panel wrong-question-entry-panel">
            <div className="panel-title">
              <BookOpenCheck size={18} />
              <h2>错题集</h2>
              <span>{wrongBook.summary.unresolved} 待重做</span>
            </div>
            <div className="wrong-question-entry">
              <div className="wrong-question-entry-metrics">
                <article>
                  <strong>{wrongBook.summary.total}</strong>
                  <span>历史错题</span>
                </article>
                <article>
                  <strong>{wrongBook.summary.chapterCount}</strong>
                  <span>涉及章节</span>
                </article>
                <article>
                  <strong>{wrongBook.summary.resolved}</strong>
                  <span>已修正</span>
                </article>
              </div>
              <p>
                错题按章节独立归档，选择题和编程题都可以重新作答。重做正确后会写回学习评估评分，并继续触发画像、知识图谱和学习路径更新。
              </p>
              <button
                className="primary-action full-width-action"
                onClick={() => navigate(`/courses/${numericCourseId}/assessment/wrong-questions`)}
                type="button"
              >
                进入错题集
                <ArrowRight size={16} />
              </button>
            </div>
          </section>
          <section className="panel assessment-loop-panel">
            <div className="panel-title">
              <Route size={18} />
              <h2>闭环规则</h2>
            </div>
            <div className="closed-loop-steps vertical">
              <span className="done">课程学习</span>
              <span className="done">笔记与导图</span>
              <span className="done">题库/代码测试</span>
              <span className="done">掌握度写回</span>
              <span className="done">路径重规划</span>
            </div>
            <p>
              评估通过后回到主线任务；评估未通过时，学习路径接口会围绕失败知识点、前置依赖和同章弱项生成补救支线。
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}

function DimensionCard({ card }: { card: AssessmentDimensionCard }) {
  const Icon = dimensionIcons[card.key] || Activity;
  return (
    <article className={`assessment-dimension-card tone-${card.tone}`}>
      <div>
        <Icon size={18} />
        <span>{card.label}</span>
      </div>
      <strong>{card.score}%</strong>
      <div className="assessment-dimension-meter" aria-label={`${card.label} ${card.score}%`}>
        <i style={{ width: `${card.score}%` }} />
      </div>
      <p>{card.detail}</p>
    </article>
  );
}
