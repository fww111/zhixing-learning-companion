import { ArrowLeft, BookOpenCheck, BrainCircuit, CheckCircle2, Code2, ListChecks, PlayCircle, RefreshCw, RotateCcw, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getCourse,
  getKnowledgeGraph,
  getReviewQueue,
  listLearningProfileEvents,
  submitAssessment,
  type Course,
  type KnowledgeGraph,
  type LearningProfileEvent,
  type ReviewQueue
} from "../api/client";
import { executeCode } from "../components/codeExecutionModel";
import { WrongQuestionTutorPanel } from "../components/WrongQuestionTutorPanel";
import { useAuth } from "../state/auth";
import {
  buildRedoAssessmentPayload,
  buildWrongQuestionBookModel,
  evaluateWrongQuestionRedo,
  type WrongQuestionBookItem,
  type WrongQuestionRedoInput
} from "./courseWrongQuestionBookModel";

export function CourseWrongQuestionsPage() {
  const { courseId } = useParams();
  const navigate = useNavigate();
  const { profile, token } = useAuth();
  const numericCourseId = Number(courseId);
  const [course, setCourse] = useState<Course>();
  const [graph, setGraph] = useState<KnowledgeGraph>();
  const [events, setEvents] = useState<LearningProfileEvent[]>([]);
  const [reviewQueue, setReviewQueue] = useState<ReviewQueue>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const model = useMemo(
    () => buildWrongQuestionBookModel({ events, nodes: graph?.nodes ?? [] }),
    [events, graph]
  );

  async function load() {
    if (!Number.isFinite(numericCourseId)) {
      setError("课程 ID 无效");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [nextCourse, nextGraph, nextEvents, nextReview] = await Promise.all([
        getCourse(token, numericCourseId),
        getKnowledgeGraph(token, numericCourseId),
        listLearningProfileEvents(token, numericCourseId).catch(() => []),
        getReviewQueue(token, numericCourseId).catch(() => undefined)
      ]);
      setCourse(nextCourse);
      setGraph(nextGraph);
      setEvents(nextEvents);
      setReviewQueue(nextReview);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载错题集失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [numericCourseId, token]);

  async function handleResolved() {
    await load();
  }

  return (
    <div className="page-stack wrong-question-book-page">
      <div className="page-heading with-actions product-page-heading">
        <div>
          <span>Wrong Question Book</span>
          <h2>{course?.name || "课程"} · 错题集</h2>
          <p>错题按章节归档。重做正确后，系统会重新写入该知识点评估结果，并同步更新画像、图谱掌握状态和后续学习路径。</p>
        </div>
        <div className="header-actions">
          <button className="secondary-action compact-button" onClick={() => navigate(`/courses/${numericCourseId}/assessment`)}>
            <ArrowLeft size={16} />
            返回评估
          </button>
          <button className="primary-action compact-button" disabled={loading} onClick={load}>
            <RefreshCw className={loading ? "spin" : ""} size={16} />
            {loading ? "刷新中" : "刷新错题"}
          </button>
        </div>
      </div>

      {error ? <div className="error">{error}</div> : null}

      {reviewQueue && reviewQueue.stats.due_count ? (
        <section className="panel wrong-book-review-banner">
          <BrainCircuit size={18} />
          <div>
            <strong>记忆引擎提醒：{reviewQueue.stats.due_count} 个知识点今天到期复习</strong>
            <p>
              {reviewQueue.items.filter((item) => item.due_today).slice(0, 3).map((item) => item.topic).join("、")}
              {reviewQueue.stats.high_risk_count ? `（含 ${reviewQueue.stats.high_risk_count} 个高危薄弱点）` : ""}。
              按艾宾浩斯间隔重做能显著提升长期记忆。
            </p>
          </div>
          <button
            className="primary-action compact-button"
            onClick={() => {
              const first = reviewQueue.items.find((item) => item.due_today);
              if (first) {
                navigate(`/courses/${numericCourseId}/knowledge/${encodeURIComponent(first.node_id)}`);
              }
            }}
            type="button"
          >
            开始复习
          </button>
        </section>
      ) : null}

      <section className="wrong-book-summary-grid">
        <article className="panel metric-panel">
          <BookOpenCheck size={20} />
          <strong>{model.summary.total}</strong>
          <span>历史错题</span>
        </article>
        <article className="panel metric-panel">
          <ShieldAlert size={20} />
          <strong>{model.summary.unresolved}</strong>
          <span>待重做</span>
        </article>
        <article className="panel metric-panel">
          <CheckCircle2 size={20} />
          <strong>{model.summary.resolved}</strong>
          <span>已修正</span>
        </article>
        <article className="panel metric-panel">
          <ListChecks size={20} />
          <strong>{model.summary.chapterCount}</strong>
          <span>涉及章节</span>
        </article>
      </section>

      {model.chapterGroups.length ? (
        <section className="wrong-book-chapter-list">
          {model.chapterGroups.map((chapter) => (
            <article className="panel wrong-book-chapter" key={chapter.chapterId}>
              <div className="wrong-book-chapter-head">
                <div>
                  <span>Chapter</span>
                  <h3>{chapter.chapterTitle}</h3>
                </div>
                <strong>{chapter.sections.reduce((sum, section) => sum + section.items.length, 0)} 题</strong>
              </div>
              <div className="wrong-book-section-list">
                {chapter.sections.map((section) => (
                  <section className="wrong-book-section" key={section.sectionId}>
                    <div className="wrong-book-section-head">
                      <h4>{section.sectionTitle}</h4>
                      <span>{section.items.filter((item) => !item.resolved).length} 待重做</span>
                    </div>
                    <div className="wrong-book-item-list">
                      {section.items.map((item) => (
                        <WrongQuestionRedoCard
                          courseId={numericCourseId}
                          item={item}
                          key={item.id}
                          onResolved={handleResolved}
                          studentId={profile?.student_id || "student-xm"}
                          token={token}
                        />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </article>
          ))}
        </section>
      ) : (
        <section className="panel wrong-book-empty">
          <BookOpenCheck size={24} />
          <h3>暂无错题</h3>
          <p>从学习路径进入知识点课堂并完成测试后，答错的选择题和未通过的编程题会按章节自动归档到这里。</p>
          <button className="primary-action compact-button" onClick={() => navigate(`/courses/${numericCourseId}/learning-path`)}>
            去学习路径
          </button>
        </section>
      )}
    </div>
  );
}

function WrongQuestionRedoCard({
  courseId,
  item,
  onResolved,
  studentId,
  token
}: {
  courseId: number;
  item: WrongQuestionBookItem;
  onResolved: () => Promise<void>;
  studentId: string;
  token?: string;
}) {
  const [selectedAnswerIndex, setSelectedAnswerIndex] = useState<number | undefined>();
  const [code, setCode] = useState(item.code || starterCodeForWrongQuestion(item));
  const [actualOutput, setActualOutput] = useState(item.actualOutput || "点击运行后显示本次输出。");
  const [attempts, setAttempts] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [running, setRunning] = useState(false);
  const [serverVerdict, setServerVerdict] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const redo: WrongQuestionRedoInput = {
    selectedAnswerIndex,
    code,
    actualOutput,
    attempts: Math.max(1, attempts)
  };
  const result = evaluateWrongQuestionRedo(item, redo, serverVerdict);
  const canSubmit = Boolean(token && !item.resolved && result.passed);

  async function runCode() {
    if (running) {
      return;
    }
    setRunning(true);
    try {
      const outcome = await executeCode({
        token,
        courseId,
        source: code,
        expectedOutput: item.expectedOutput || ""
      });
      const output = outcome.output;
      setActualOutput(output);
      setServerVerdict(outcome.verdict);
      const nextAttempts = attempts + 1;
      setAttempts(nextAttempts);
      const nextResult = evaluateWrongQuestionRedo(item, {
        ...redo,
        actualOutput: output,
        attempts: nextAttempts
      }, outcome.verdict);
      const passed = nextResult.passed;
      setFeedback(
        `${passed ? "真实运行判分通过" : outcome.message || "运行结果与期望不一致"}${outcome.serverVerified ? "" : "（离线模拟，仅供参考）"}`
      );
    } finally {
      setRunning(false);
    }
  }

  async function submitRedo() {
    if (!token || !canSubmit) {
      return;
    }
    setSubmitting(true);
    setFeedback("");
    try {
      const payload = buildRedoAssessmentPayload({
        courseId,
        item,
        redo,
        studentId,
        serverVerdict
      });
      await submitAssessment(token, payload);
      setFeedback("重做正确，评估结果已写回。");
      await onResolved();
    } catch (caught) {
      setFeedback(caught instanceof Error ? caught.message : "提交错题重做失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <article className={`wrong-book-item ${item.type} ${item.resolved ? "resolved" : ""}`}>
      <div className="wrong-book-item-main">
        <div className="wrong-book-item-head">
          <span className={`wrong-type-badge ${item.type}`}>{item.type === "code" ? <Code2 size={14} /> : <ListChecks size={14} />}{item.type === "code" ? "编程题" : item.dimension}</span>
          <strong>{item.nodeTitle}</strong>
          {item.resolved ? <em>已修正</em> : <em className="pending">待重做</em>}
        </div>
        <p>{item.prompt}</p>
        <div className="wrong-answer-compare">
          <div>
            <span>原答案</span>
            <strong>{item.selectedAnswer}</strong>
          </div>
          <div>
            <span>正确要求</span>
            <strong>{item.correctAnswer}</strong>
          </div>
        </div>
        <WrongQuestionTutorPanel courseId={courseId} item={item} />
      </div>

      {!item.resolved ? (
        <div className="wrong-redo-area">
          {item.type === "quiz" ? (
            <div className="wrong-redo-options">
              {(item.options || []).map((option, optionIndex) => (
                <button
                  className={selectedAnswerIndex === optionIndex ? "selected" : ""}
                  key={`${item.id}-${optionIndex}`}
                  onClick={() => {
                    setSelectedAnswerIndex(optionIndex);
                    setFeedback(evaluateWrongQuestionRedo(item, { selectedAnswerIndex: optionIndex }).message);
                  }}
                  type="button"
                >
                  <span>{String.fromCharCode(65 + optionIndex)}</span>
                  {option}
                </button>
              ))}
            </div>
          ) : (
            <div className="wrong-redo-code-grid">
              <div className="code-editor-shell">
                <div className="code-toolbar">
                  <span>Redo Code</span>
                  <div>
                    <button className="secondary-action compact-button" onClick={() => {
                      setCode(starterCodeForWrongQuestion(item));
                      setActualOutput("点击运行后显示本次输出。");
                      setAttempts(0);
                    }} type="button">
                      <RotateCcw size={14} />
                      重置
                    </button>
                    <button className="primary-action compact-button" disabled={running} onClick={runCode} type="button">
                      <PlayCircle size={14} />
                      {running ? "沙箱运行中…" : "运行"}
                    </button>
                  </div>
                </div>
                <textarea aria-label="错题重做代码编辑器" onChange={(event) => setCode(event.target.value)} value={code} />
              </div>
              <div className="assessment-output-panel">
                <span>
                  本次输出
                  {serverVerdict ? (
                    <em className={`sandbox-badge ${serverVerdict === "accepted" ? "ok" : "warn"}`}>
                      服务端沙箱 · {serverVerdict === "accepted" ? "判分通过" : serverVerdict === "wrong_answer" ? "输出不一致" : serverVerdict === "compile_error" ? "编译失败" : serverVerdict === "timeout" ? "运行超时" : "运行出错"}
                    </em>
                  ) : null}
                </span>
                <pre>{actualOutput}</pre>
                <small>期望输出</small>
                <pre>{item.expectedOutput || "-"}</pre>
              </div>
            </div>
          )}
          <div className="wrong-redo-footer">
            <span className={result.passed ? "pass" : ""}>{feedback || result.message}</span>
            <button className="primary-action compact-button" disabled={!canSubmit || submitting} onClick={submitRedo} type="button">
              {submitting ? "写回中" : "提交重做并更新评分"}
            </button>
          </div>
        </div>
      ) : (
        <div className="wrong-resolved-note">
          <CheckCircle2 size={16} />
          <span>已于 {formatTime(item.resolvedAt)} 重做通过，保留为学习历史。</span>
        </div>
      )}
    </article>
  );
}

function starterCodeForWrongQuestion(item: WrongQuestionBookItem): string {
  if (item.code?.trim()) {
    return item.code;
  }
  return [
    "# 根据题目要求补全代码",
    "# 运行输出需要与期望输出完全一致",
    ""
  ].join("\n");
}

function formatTime(value?: string): string {
  if (!value) {
    return "最近";
  }
  return value.replace("T", " ").replace("Z", "").slice(0, 16);
}
