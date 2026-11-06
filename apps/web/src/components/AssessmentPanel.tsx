import { useMemo, useState } from "react";
import { Activity, CheckCircle2, Code2, ListChecks, PlayCircle, RefreshCw, Target } from "lucide-react";
import { submitAssessment, type AssessmentReport, type LessonState, type Resource } from "../api/client";
import {
  buildAssessmentQuizItems,
  buildComprehensiveAssessmentPayload,
  buildCodeAssessmentChallenge,
  clampScore,
  codeAttemptMatchesChallenge,
  masteryStatusLabel,
  previewQuizScore
} from "./assessmentModel";
import { executeCode } from "./codeExecutionModel";
import { isInlineCodeRunSuccessful, runInlinePythonLikeCode } from "./postClassroomExperienceModel";

interface AssessmentPanelProps {
  courseId?: number;
  exerciseResource?: Resource;
  hasResult: boolean;
  initialScore?: number;
  lessonState?: LessonState;
  nodeId?: string;
  onCodePassed?: () => void;
  onSubmitted?: (report: AssessmentReport, score: number) => void;
  studentId?: string;
  token?: string;
  topic?: string;
  courseName?: string;
}

function percentValue(score: number | undefined): number {
  return Math.round(clampScore(score ?? 0) * 100);
}

function reportScore(report: AssessmentReport | undefined, fallback: number): number {
  return report?.final_score ?? fallback;
}

export function AssessmentPanel({
  courseId,
  exerciseResource,
  hasResult,
  initialScore = 0.58,
  lessonState,
  nodeId,
  onCodePassed,
  onSubmitted,
  studentId = "student-xm",
  token,
  topic = "当前知识点",
  courseName = ""
}: AssessmentPanelProps) {
  const exerciseContent = exerciseResource?.content || "";
  const quizItems = useMemo(
    () => buildAssessmentQuizItems({ courseName, exerciseContent, topic }),
    [courseName, exerciseContent, topic]
  );
  const codeChallenge = useMemo(
    () => buildCodeAssessmentChallenge({ courseName, exerciseContent, topic }),
    [courseName, exerciseContent, topic]
  );
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [code, setCode] = useState(codeChallenge.starterCode);
  const [codeOutput, setCodeOutput] = useState("点击运行后，这里会显示浏览器内即时输出。");
  const [codePassed, setCodePassed] = useState(false);
  const [codeAttempts, setCodeAttempts] = useState(0);
  const [codeRunning, setCodeRunning] = useState(false);
  const [serverVerdict, setServerVerdict] = useState<string | null>(null);
  const [offlineRun, setOfflineRun] = useState(false);
  const [report, setReport] = useState<AssessmentReport>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const canSubmit = Boolean(hasResult && token && courseId && nodeId);
  const answeredCount = Object.keys(answers).length;
  const allAnswered = answeredCount === quizItems.length;
  const quizScore = useMemo(() => previewQuizScore(answers, quizItems), [answers, quizItems]);
  const currentScore = reportScore(report, allAnswered || codeAttempts ? (
    (Boolean(lessonState?.classroom_completed) ? 0.15 : 0) +
    quizScore * 0.3 +
    (codePassed ? 0.35 : code.trim() ? 0.09 : 0) +
    (
      [
        Boolean(lessonState?.notes_completed),
        Boolean(lessonState?.mind_map_completed),
        Boolean(lessonState?.code_lab_completed || codePassed)
      ].filter(Boolean).length / 3
    ) * 0.2
  ) : initialScore);
  const percent = percentValue(currentScore);

  async function runCode() {
    if (codeRunning) {
      return;
    }
    setCodeRunning(true);
    setCodeAttempts((current) => current + 1);
    try {
      const outcome = await executeCode({
        token,
        courseId,
        source: code,
        expectedOutput: codeChallenge.expectedOutput
      });
      const output = outcome.output;
      setCodeOutput(output);
      setServerVerdict(outcome.verdict);
      setOfflineRun(!outcome.serverVerified);
      const nextPassed = outcome.serverVerified
        ? Boolean(outcome.passed)
        : isInlineCodeRunSuccessful(output) && codeAttemptMatchesChallenge(codeChallenge.expectedOutput, output);
      setCodePassed(nextPassed);
      if (nextPassed) {
        onCodePassed?.();
      }
    } finally {
      setCodeRunning(false);
    }
  }

  async function handleSubmit() {
    if (!canSubmit || !token || !courseId || !nodeId) {
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const payload = buildComprehensiveAssessmentPayload({
        answers,
        codeAttempt: {
          prompt: codeChallenge.prompt,
          code,
          expectedOutput: codeChallenge.expectedOutput,
          actualOutput: codeOutput,
          passed: codePassed,
          attempts: Math.max(1, codeAttempts),
          serverVerdict
        },
        quizItems,
        courseId,
        lessonState,
        nodeId,
        studentId,
        topic
      });
      const nextReport = await submitAssessment(token, payload);
      const nextScore = nextReport.final_score ?? currentScore;
      setReport(nextReport);
      onSubmitted?.(nextReport, nextScore);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提交学习评估失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel assessment-result-panel">
      <div className="panel-title">
        <Activity size={18} />
        <h2>多维课堂评估</h2>
        <span>{report?.passed ? "已通过" : "动态调整"}</span>
      </div>
      {hasResult ? (
        <div className="assessment">
          <div className="grid-3 assessment-score-grid">
            <div className="metric"><span>综合得分</span><strong>{percent}</strong><small>{report?.passed ?? percent >= 75 ? "已达标" : "未达标"}</small></div>
            <div className="metric"><span>通过阈值</span><strong>75</strong><small>含代码题约束</small></div>
            <div className="metric"><span>掌握状态</span><strong>{masteryStatusLabel(currentScore)}</strong><small>同步图谱颜色</small></div>
          </div>

          <div className="assessment-dimension-grid">
            <article>
              <Target size={16} />
              <strong>课堂</strong>
              <span>{lessonState?.classroom_completed ? "已完成" : "待完成"}</span>
            </article>
            <article>
              <ListChecks size={16} />
              <strong>题库</strong>
              <span>{percentValue(quizScore)}%</span>
            </article>
            <article>
              <Code2 size={16} />
              <strong>编程</strong>
              <span>{codePassed ? "已通过" : "待通过"}</span>
            </article>
          </div>

          <div className="quiz-question-list">
            {quizItems.map((item, index) => (
              <article className="quiz-question-card" key={item.id}>
                <div className="quiz-question-head">
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <strong>{item.prompt}</strong>
                    <small>{item.dimension} · 权重 {Math.round(item.weight * 100)}%</small>
                  </div>
                </div>
                <div className="quiz-option-list">
                  {item.options.map((option, optionIndex) => (
                    <button
                      className={answers[item.id] === optionIndex ? "selected" : ""}
                      disabled={!canSubmit || submitting}
                      key={option}
                      onClick={() => setAnswers((current) => ({ ...current, [item.id]: optionIndex }))}
                      type="button"
                    >
                      <span>{String.fromCharCode(65 + optionIndex)}</span>
                      {option}
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>

          <article className="assessment-programming-card">
            <div className="quiz-question-head">
              <span>04</span>
              <div>
                <strong>编程题：用代码验证本节知识点</strong>
                <small>代码将提交到服务端沙箱真实编译运行，判分结果可信且计入评估</small>
              </div>
            </div>
            <p className="assessment-code-prompt">{codeChallenge.prompt}</p>
            <div className="assessment-code-grid">
              <div className="code-editor-shell">
                <div className="code-toolbar">
                  <span>Python Practice</span>
                  <div>
                    <button className="secondary-action compact-button" onClick={() => {
                      setCode(codeChallenge.starterCode);
                      setCodeOutput("点击运行后，这里会显示浏览器内即时输出。");
                      setCodePassed(false);
                    }} type="button">
                      <RefreshCw size={15} />
                      重置
                    </button>
                    <button className="primary-action compact-button" disabled={codeRunning} onClick={runCode} type="button">
                      <PlayCircle size={15} />
                      运行代码
                    </button>
                  </div>
                </div>
                <textarea aria-label="课堂评估编程题编辑器" onChange={(event) => setCode(event.target.value)} value={code} />
              </div>
              <div className="assessment-output-panel">
                <span>
                  运行输出
                  {serverVerdict ? (
                    <em className={`sandbox-badge ${serverVerdict === "accepted" ? "ok" : "warn"}`}>
                      服务端沙箱 · {serverVerdict === "accepted" ? "判分通过" : serverVerdict === "wrong_answer" ? "输出不一致" : serverVerdict === "compile_error" ? "编译失败" : serverVerdict === "timeout" ? "运行超时" : "运行出错"}
                    </em>
                  ) : offlineRun ? (
                    <em className="sandbox-badge offline">离线模拟（后端不可用）</em>
                  ) : null}
                </span>
                <pre>{codeOutput}</pre>
                <small>{codePassed ? "真实运行判分通过，已记录为代码实践证据。" : "需要真实运行并与题目要求的输出一致才算通过。"}</small>
              </div>
            </div>
          </article>

          {report?.dimension_scores ? (
            <div className="assessment-report-grid">
              {Object.entries(report.dimension_scores).map(([key, value]) => (
                <article key={key}>
                  <span>{dimensionLabel(key)}</span>
                  <strong>{percentValue(value)}%</strong>
                </article>
              ))}
            </div>
          ) : null}

          <div>
            <span>{topic} 综合掌握度</span>
            <strong>{percent}% · {masteryStatusLabel(currentScore)}</strong>
          </div>
          <div className="progress"><span style={{ width: `${percent}%` }} /></div>
          <button className="primary-action" disabled={!canSubmit || submitting || !allAnswered || codeAttempts === 0} onClick={handleSubmit} type="button">
            {submitting ? "提交中" : "完成课堂测试并更新学习规划"}
          </button>
          {report ? (
            <div className={`assessment-pass-badge ${report.passed ? "pass" : "fail"}`}>
              <CheckCircle2 size={16} />
              <span>{report.next_adjustment}</span>
            </div>
          ) : (
            <p>提交后系统会综合课堂完成、选择题、编程题、学习行为证据，更新知识图谱节点颜色、学生画像，并触发下一轮学习路径规划。</p>
          )}
          {report?.feedback?.length ? (
            <ul className="assessment-feedback-list">
              {report.feedback.map((item) => <li key={item}>{item}</li>)}
            </ul>
          ) : null}
          {report?.profile_update?.event_id ? (
            <article className="profile-update-summary">
              <div>
                <strong>画像随学随新</strong>
                <span>{report.profile_update.replan_required ? "已触发路径重规划" : "已记录画像证据"}</span>
              </div>
              <p>{report.profile_update.update_reason}</p>
              {report.profile_update.changed_dimensions?.length ? (
                <small>更新维度：{report.profile_update.changed_dimensions.join(" / ")}</small>
              ) : null}
              {report.profile_update.profile_summary ? (
                <blockquote>{report.profile_update.profile_summary}</blockquote>
              ) : null}
            </article>
          ) : null}
          {error ? <p className="error compact-error">{error}</p> : null}
        </div>
      ) : (
        <p className="empty">完成课堂学习后，系统会开放随堂评估。</p>
      )}
    </section>
  );
}

function dimensionLabel(key: string): string {
  const labels: Record<string, string> = {
    classroom: "课堂完成",
    quiz: "选择题",
    code: "编程题",
    behavior: "学习行为"
  };
  return labels[key] || key;
}
