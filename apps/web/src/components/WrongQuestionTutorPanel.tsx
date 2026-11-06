import { AlertTriangle, BadgeCheck, BookMarked, BrainCircuit, CheckCircle2, ChevronRight, Loader2, ListChecks, MessageCircleQuestion, PenLine, Sparkles, Target, XCircle } from "lucide-react";
import { useState } from "react";
import { marked } from "marked";
import {
  explainWrongQuestion,
  generateWrongQuestionVariations,
  submitAssessment,
  submitInteractiveAnswer,
  type InteractiveAnswerVerdict,
  type WrongQuestionExplanation
} from "../api/client";
import { useAuth } from "../state/auth";
import type { WrongQuestionBookItem } from "../pages/courseWrongQuestionBookModel";
import {
  advanceAfterVerdict,
  buildTutorContext,
  buildVariationAssessmentPayload,
  currentPracticeQuestion,
  initialPracticeState,
  recordAnswer,
  summarizePractice,
  type PracticeState
} from "../pages/wrongQuestionTutorModel";

type ExplainStatus = "idle" | "loading" | "ready" | "error";

/**
 * 错题三步闭环（AI 助教）：讲清楚 → 拓展同类题 → AI 问学生答。
 * 讲解与点评基于课程知识库证据（chunk 溯源），变式练习战报可写回掌握度。
 */
export function WrongQuestionTutorPanel({ courseId, item }: { courseId: number; item: WrongQuestionBookItem }) {
  const { profile, token } = useAuth();
  const [explainStatus, setExplainStatus] = useState<ExplainStatus>("idle");
  const [explanation, setExplanation] = useState<WrongQuestionExplanation>();
  const [explainError, setExplainError] = useState("");
  const [practice, setPractice] = useState<PracticeState>();
  const [practiceError, setPracticeError] = useState("");
  const [selectedAnswerIndex, setSelectedAnswerIndex] = useState<number>();
  const [answerText, setAnswerText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [writingBack, setWritingBack] = useState(false);
  const [writtenBack, setWrittenBack] = useState(false);

  const question = practice ? currentPracticeQuestion(practice) : undefined;
  const summary = practice ? summarizePractice(practice) : undefined;

  async function handleExplain() {
    if (!token || explainStatus === "loading") {
      return;
    }
    setExplainStatus("loading");
    setExplainError("");
    try {
      const result = await explainWrongQuestion(token, buildTutorContext(item, courseId));
      setExplanation(result);
      setExplainStatus("ready");
    } catch (caught) {
      setExplainError(caught instanceof Error ? caught.message : "AI 讲解失败，请稍后重试");
      setExplainStatus("error");
    }
  }

  async function handleStartPractice() {
    if (!token || submitting) {
      return;
    }
    setSubmitting(true);
    setPracticeError("");
    try {
      const bundle = await generateWrongQuestionVariations(token, buildTutorContext(item, courseId));
      if (!bundle.questions.length) {
        throw new Error("AI 暂时没有生成出可用的拓展题，请稍后再试");
      }
      setPractice({ ...initialPracticeState(), stage: "answering", bundle });
      setSelectedAnswerIndex(undefined);
      setAnswerText("");
    } catch (caught) {
      setPracticeError(caught instanceof Error ? caught.message : "生成拓展题失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmitAnswer() {
    if (!token || !practice || !question || submitting) {
      return;
    }
    const hasQuizAnswer = question.question_type === "quiz" && selectedAnswerIndex !== undefined;
    const hasTextAnswer = question.question_type === "short_answer" && answerText.trim().length > 0;
    if (!hasQuizAnswer && !hasTextAnswer) {
      return;
    }
    setSubmitting(true);
    setPracticeError("");
    try {
      const verdict: InteractiveAnswerVerdict = await submitInteractiveAnswer(token, {
        course_id: courseId,
        node_id: item.nodeId,
        topic: item.topic || item.nodeTitle,
        question,
        student_answer_index: selectedAnswerIndex,
        student_answer_text: answerText.trim()
      });
      setPractice(
        recordAnswer(practice, question, verdict, {
          studentAnswerIndex: selectedAnswerIndex,
          studentAnswerText: answerText.trim()
        })
      );
    } catch (caught) {
      setPracticeError(caught instanceof Error ? caught.message : "提交回答失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  function handleNextQuestion() {
    setPractice((current) => (current ? advanceAfterVerdict(current) : current));
    setSelectedAnswerIndex(undefined);
    setAnswerText("");
  }

  async function handleWriteBack() {
    if (!token || !practice || writingBack) {
      return;
    }
    setWritingBack(true);
    setPracticeError("");
    try {
      await submitAssessment(
        token,
        buildVariationAssessmentPayload({
          courseId,
          studentId: profile?.student_id || "student-xm",
          item,
          state: practice
        })
      );
      setWrittenBack(true);
    } catch (caught) {
      setPracticeError(caught instanceof Error ? caught.message : "写回评估失败，请稍后重试");
    } finally {
      setWritingBack(false);
    }
  }

  return (
    <div className="wrong-tutor">
      {explainStatus === "idle" ? (
        <button className="wrong-tutor-launch secondary-action compact-button" onClick={handleExplain} type="button">
          <BrainCircuit size={15} />
          AI 助教讲透这道题
        </button>
      ) : null}

      {explainStatus === "loading" ? (
        <div className="wrong-tutor-loading">
          <Loader2 className="spin" size={16} />
          <span>AI 助教正在检索课程证据、分析错因…</span>
        </div>
      ) : null}

      {explainStatus === "error" ? (
        <div className="wrong-tutor-error">
          <AlertTriangle size={15} />
          <span>{explainError}</span>
          <button className="secondary-action compact-button" onClick={handleExplain} type="button">
            重试
          </button>
        </div>
      ) : null}

      {explainStatus === "ready" && explanation ? (
        <div className="wrong-tutor-explanation">
          <div className="wrong-tutor-diagnosis">
            <span>
              <Target size={14} />
              错因诊断
            </span>
            <p>{explanation.diagnosis}</p>
          </div>
          <div className="wrong-tutor-explain-body" dangerouslySetInnerHTML={{ __html: marked.parse(explanation.explanation, { async: false }) as string }} />
          {explanation.key_points.length ? (
            <ul className="wrong-tutor-key-points">
              {explanation.key_points.map((point, index) => (
                <li key={`${index}-${point.slice(0, 12)}`}>
                  <BadgeCheck size={14} />
                  {point}
                </li>
              ))}
            </ul>
          ) : null}
          {explanation.evidence_chunks.length ? (
            <div className="wrong-tutor-evidence">
              <span>
                <BookMarked size={13} />
                讲解依据（课程原文溯源）
              </span>
              <ul>
                {explanation.evidence_chunks.map((chunk) => (
                  <li key={String(chunk.chunk_id ?? chunk.heading)}>
                    <em>chunk#{chunk.chunk_id ?? "?"}</em>
                    <strong>{chunk.heading}</strong>
                    <small>{chunk.source_locator}</small>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {practice ? null : (
            <button className="wrong-tutor-expand primary-action compact-button" disabled={submitting} onClick={handleStartPractice} type="button">
              <Sparkles size={15} />
              {submitting ? "正在生成拓展题…" : "拓展此类问题，AI 出题考我"}
            </button>
          )}
          {practiceError ? (
            <div className="wrong-tutor-error">
              <AlertTriangle size={15} />
              <span>{practiceError}</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {practice && question ? (
        <div className="wrong-tutor-practice">
          <div className="wrong-tutor-practice-head">
            <span className="wrong-tutor-practice-progress">
              AI 出题 · 第 {practice.currentIndex + 1}/{practice.bundle?.questions.length} 题
            </span>
            <span className="wrong-tutor-meta">
              <em>{question.difficulty}</em>
              {question.focus ? <em>{question.focus}</em> : null}
            </span>
          </div>

          {practice.stage === "answering" ? (
            <div className="wrong-tutor-question">
              <p>
                <MessageCircleQuestion size={15} />
                {question.prompt}
              </p>
              {question.question_type === "quiz" ? (
                <div className="wrong-tutor-options">
                  {question.options.map((option, optionIndex) => (
                    <button
                      className={selectedAnswerIndex === optionIndex ? "selected" : ""}
                      key={`${question.id}-${optionIndex}`}
                      onClick={() => setSelectedAnswerIndex(optionIndex)}
                      type="button"
                    >
                      <span>{String.fromCharCode(65 + optionIndex)}</span>
                      {option}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="wrong-tutor-text-answer">
                  <textarea
                    aria-label="拓展题简答输入"
                    onChange={(event) => setAnswerText(event.target.value)}
                    placeholder="用你的话回答（AI 会基于课程知识点评）"
                    value={answerText}
                  />
                  <small>
                    <PenLine size={12} />
                    简答题由 AI 对照课程知识判分
                  </small>
                </div>
              )}
              <button
                className="primary-action compact-button"
                disabled={submitting || (selectedAnswerIndex === undefined && !answerText.trim())}
                onClick={handleSubmitAnswer}
                type="button"
              >
                {submitting ? "AI 点评中…" : "提交回答，AI 点评"}
              </button>
            </div>
          ) : null}

          {practice.stage === "verdict" && practice.verdict ? (
            <div className={`wrong-tutor-verdict ${practice.verdict.correct ? "pass" : "fail"}`}>
              <div className="wrong-tutor-verdict-head">
                {practice.verdict.correct ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
                <strong>{practice.verdict.correct ? "回答正确" : "未命中要点"}</strong>
                <em>{practice.verdict.score} 分</em>
              </div>
              <p>{practice.verdict.comment}</p>
              {!practice.verdict.correct && practice.verdict.reference_answer ? (
                <div className="wrong-tutor-reference">
                  <span>参考答案</span>
                  <p>{practice.verdict.reference_answer}</p>
                </div>
              ) : null}
              <button className="primary-action compact-button" onClick={handleNextQuestion} type="button">
                {practice.currentIndex + 1 >= (practice.bundle?.questions.length || 0) ? "完成练习，看战报" : "下一题"}
                <ChevronRight size={14} />
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {practice?.stage === "finished" && summary ? (
        <div className="wrong-tutor-report">
          <div className="wrong-tutor-report-head">
            <ListChecks size={16} />
            <strong>拓展练习战报</strong>
            <span>
              {summary.correctCount}/{summary.total} 题答对 · 平均 {summary.averageScore} 分
            </span>
          </div>
          {summary.weakFocuses.length ? (
            <p className="wrong-tutor-report-weak">
              还需巩固：
              {summary.weakFocuses.map((focus) => (
                <em key={focus}>{focus}</em>
              ))}
            </p>
          ) : (
            <p className="wrong-tutor-report-weak all-good">全部答对，该知识点的同类变式已经掌握。</p>
          )}
          {writtenBack ? (
            <div className="wrong-tutor-written">
              <CheckCircle2 size={15} />
              <span>已计入掌握度：本次拓展练习将更新该知识点的画像、图谱颜色与学习路径。</span>
            </div>
          ) : (
            <button className="secondary-action compact-button" disabled={writingBack} onClick={handleWriteBack} type="button">
              {writingBack ? "写回中…" : "将本次练习计入掌握度"}
            </button>
          )}
        </div>
      ) : null}
    </div>
  );
}
