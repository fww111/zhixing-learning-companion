import type {
  ComprehensiveAssessmentPayload,
  InteractiveAnswerVerdict,
  VariationBundle,
  VariationQuestion,
  WrongQuestionContextPayload
} from "../api/client";
import type { WrongQuestionBookItem } from "./courseWrongQuestionBookModel";

/** 互动练习阶段：出题中 → 作答 → 点评 → 全部完成 */
export type VariationPracticeStage = "loading" | "answering" | "verdict" | "finished";

export interface PracticeAnswerRecord {
  questionId: string;
  questionType: VariationQuestion["question_type"];
  focus: string;
  studentAnswerIndex?: number;
  studentAnswerText: string;
  correct: boolean;
  score: number;
}

export interface PracticeSummary {
  total: number;
  correctCount: number;
  scoreSum: number;
  averageScore: number;
  weakFocuses: string[];
  allCorrect: boolean;
}

/** 从错题卡片构造后端上下文（讲解 / 变式题共用）。 */
export function buildTutorContext(item: WrongQuestionBookItem, courseId: number): WrongQuestionContextPayload {
  return {
    course_id: courseId,
    node_id: item.nodeId,
    topic: item.topic || item.nodeTitle,
    question_type: item.type,
    prompt: item.prompt,
    options: item.options || [],
    selected_answer: item.selectedAnswer || "",
    correct_answer: item.correctAnswer || "",
    code: item.code || "",
    actual_output: item.actualOutput || "",
    expected_output: item.expectedOutput || "",
    attempts: Math.max(1, item.attempts)
  };
}

export interface PracticeState {
  stage: VariationPracticeStage;
  bundle?: VariationBundle;
  currentIndex: number;
  records: PracticeAnswerRecord[];
  verdict?: InteractiveAnswerVerdict;
  error: string;
}

export function initialPracticeState(): PracticeState {
  return { stage: "loading", currentIndex: 0, records: [], error: "" };
}

export function currentPracticeQuestion(state: PracticeState): VariationQuestion | undefined {
  return state.bundle?.questions[state.currentIndex];
}

/** 提交作答后：记录结果并推进到点评态；答完最后一题进入 finished。 */
export function recordAnswer(
  state: PracticeState,
  question: VariationQuestion,
  verdict: InteractiveAnswerVerdict,
  answer: { studentAnswerIndex?: number; studentAnswerText: string }
): PracticeState {
  const record: PracticeAnswerRecord = {
    questionId: question.id,
    questionType: question.question_type,
    focus: question.focus,
    studentAnswerIndex: answer.studentAnswerIndex,
    studentAnswerText: answer.studentAnswerText,
    correct: verdict.correct,
    score: verdict.score
  };
  const records = [...state.records, record];
  return {
    ...state,
    stage: "verdict",
    records,
    verdict
  };
}

/** 点评页点击"下一题/完成练习"后的状态推进。 */
export function advanceAfterVerdict(state: PracticeState): PracticeState {
  const total = state.bundle?.questions.length || 0;
  const nextIndex = state.currentIndex + 1;
  if (nextIndex >= total) {
    return { ...state, stage: "finished", verdict: undefined };
  }
  return { ...state, stage: "answering", currentIndex: nextIndex, verdict: undefined };
}

/** 练习战报：答对数、平均分、薄弱考察点。 */
export function summarizePractice(state: PracticeState): PracticeSummary {
  const records = state.records;
  const total = records.length;
  const correctCount = records.filter((record) => record.correct).length;
  const scoreSum = records.reduce((sum, record) => sum + record.score, 0);
  const weakFocuses = [
    ...new Set(records.filter((record) => !record.correct && record.focus).map((record) => record.focus))
  ];
  return {
    total,
    correctCount,
    scoreSum,
    averageScore: total ? Math.round(scoreSum / total) : 0,
    weakFocuses,
    allCorrect: total > 0 && correctCount === total
  };
}

/** 拓展练习写回评估：每道变式题一条 quiz_answer，计入掌握度闭环（不标记原错题已解决）。 */
export function buildVariationAssessmentPayload(input: {
  courseId: number;
  studentId: string;
  item: WrongQuestionBookItem;
  state: PracticeState;
}): ComprehensiveAssessmentPayload {
  const summary = summarizePractice(input.state);
  const quizAnswers = input.state.records.map((record, index) => {
    const question = input.state.bundle?.questions.find((candidate) => candidate.id === record.questionId);
    return {
      id: `variation_${record.questionId}`,
      dimension: `拓展练习·${record.focus || question?.difficulty || "巩固"}`,
      correct: record.correct,
      prompt: question?.prompt || record.questionId,
      options: record.questionType === "quiz" ? question?.options || [] : [],
      correct_answer_index: record.questionType === "quiz" ? question?.correct_answer_index ?? undefined : undefined,
      selected_answer_index: record.studentAnswerIndex,
      weight: 1
    };
  });

  return {
    student_id: input.studentId,
    topic: input.item.topic,
    course_id: input.courseId,
    knowledge_node_id: input.item.nodeId,
    classroom_completed: true,
    notes_completed: true,
    mind_map_completed: true,
    code_lab_completed: true,
    quiz_answers: quizAnswers,
    detail: JSON.stringify({
      assessment_type: "wrong_question_variation_practice",
      source_question_id: input.item.id,
      source_event_id: input.item.sourceEventId,
      variation_practice: {
        total: summary.total,
        correct: summary.correctCount,
        average_score: summary.averageScore,
        weak_focuses: summary.weakFocuses
      }
    })
  };
}
