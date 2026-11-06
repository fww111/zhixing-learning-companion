import type { InteractiveAnswerVerdict, VariationBundle, VariationQuestion } from "../api/client.js";
import type { WrongQuestionBookItem } from "./courseWrongQuestionBookModel.js";
import {
  advanceAfterVerdict,
  buildTutorContext,
  buildVariationAssessmentPayload,
  currentPracticeQuestion,
  initialPracticeState,
  recordAnswer,
  summarizePractice,
  type PracticeState
} from "./wrongQuestionTutorModel.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual<T>(actual: T, expected: T, label: string) {
  const same = Object.is(actual, expected)
    || (typeof actual === "object" && typeof expected === "object"
      && JSON.stringify(actual) === JSON.stringify(expected));
  if (!same) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)} but got ${JSON.stringify(actual)}`);
  }
}

function wrongItem(overrides: Partial<WrongQuestionBookItem> = {}): WrongQuestionBookItem {
  return {
    id: "12-quiz-q1",
    questionId: "q1",
    sourceEventId: 12,
    type: "quiz",
    topic: "变量与标识符",
    nodeId: "node-1-2",
    dimension: "概念理解",
    prompt: "下列哪个变量名不合法？",
    options: ["_my_var", "2nd_value"],
    selectedAnswerIndex: 0,
    correctAnswerIndex: 1,
    selectedAnswer: "_my_var",
    correctAnswer: "2nd_value",
    attempts: 1,
    createdAt: "2026-11-01T10:00:00",
    resolved: false,
    chapterId: "chapter-1",
    chapterTitle: "第1章 基础",
    sectionId: "section-1-1",
    sectionTitle: "变量",
    nodeTitle: "1.2 变量与标识符",
    ...overrides
  };
}

function quizQuestion(overrides: Partial<VariationQuestion> = {}): VariationQuestion {
  return {
    id: "v1",
    question_type: "quiz",
    prompt: "变式选择题",
    options: ["甲", "乙"],
    correct_answer_index: 1,
    reference_answer: "",
    focus: "概念辨析",
    difficulty: "基础",
    ...overrides
  };
}

function verdict(correct: boolean, score: number): InteractiveAnswerVerdict {
  return { correct, score, comment: "点评", reference_answer: "", focus: "概念辨析" };
}

function bundleWith(questions: VariationQuestion[]): VariationBundle {
  return {
    node_id: "node-1-2",
    topic: "变量与标识符",
    source_question_type: "quiz",
    questions,
    evidence_chunks: []
  };
}

function testBuildTutorContext() {
  const context = buildTutorContext(wrongItem(), 3);
  assertEqual(context.course_id, 3, "course_id");
  assertEqual(context.node_id, "node-1-2", "node_id");
  assertEqual(context.topic, "变量与标识符", "topic");
  assertEqual(context.question_type, "quiz", "question_type");
  assertEqual(context.options, ["_my_var", "2nd_value"], "options");
  assertEqual(context.selected_answer, "_my_var", "selected_answer");
  assertEqual(context.correct_answer, "2nd_value", "correct_answer");

  const codeContext = buildTutorContext(
    wrongItem({
      type: "code",
      topic: "",
      code: "print(total)",
      actualOutput: "0",
      expectedOutput: "15",
      attempts: 0
    }),
    3
  );
  assertEqual(codeContext.question_type, "code", "code question_type");
  assertEqual(codeContext.topic, "1.2 变量与标识符", "code topic fallback");
  assertEqual(codeContext.code, "print(total)", "code body");
  assertEqual(codeContext.expected_output, "15", "expected_output");
  assertEqual(codeContext.attempts, 1, "attempts min 1");
}

function testPracticeStateFlow() {
  const questions = [quizQuestion({ id: "v1" }), quizQuestion({ id: "v2" })];
  let state: PracticeState = { ...initialPracticeState(), stage: "answering", bundle: bundleWith(questions) };
  assertEqual(currentPracticeQuestion(state)?.id, "v1", "first question");

  state = recordAnswer(state, questions[0]!, verdict(true, 90), { studentAnswerIndex: 1, studentAnswerText: "" });
  assertEqual(state.stage, "verdict", "stage after answer");
  assertEqual(state.records.length, 1, "records after answer");
  assertEqual(state.records[0]!.correct, true, "record correct");

  state = advanceAfterVerdict(state);
  assertEqual(state.stage, "answering", "stage after advance");
  assertEqual(state.currentIndex, 1, "index after advance");
  assertEqual(state.verdict, undefined, "verdict cleared");
  assertEqual(currentPracticeQuestion(state)?.id, "v2", "second question");

  state = recordAnswer(state, questions[1]!, verdict(false, 30), { studentAnswerIndex: 0, studentAnswerText: "" });
  state = advanceAfterVerdict(state);
  assertEqual(state.stage, "finished", "stage finished");
  assertEqual(summarizePractice(state).total, 2, "summary total");
}

function testSummarizePractice() {
  const questions = [
    quizQuestion({ id: "v1", focus: "概念辨析" }),
    quizQuestion({ id: "v2", focus: "迁移应用" })
  ];
  let state: PracticeState = { ...initialPracticeState(), stage: "answering", bundle: bundleWith(questions) };
  state = recordAnswer(state, questions[0]!, verdict(true, 100), { studentAnswerIndex: 1, studentAnswerText: "" });
  state = recordAnswer(state, questions[1]!, verdict(false, 40), { studentAnswerIndex: 0, studentAnswerText: "" });

  const summary = summarizePractice(state);
  assertEqual(summary.total, 2, "summary total");
  assertEqual(summary.correctCount, 1, "summary correctCount");
  assertEqual(summary.averageScore, 70, "summary averageScore");
  assertEqual(summary.weakFocuses, ["迁移应用"], "summary weakFocuses");
  assertEqual(summary.allCorrect, false, "summary allCorrect");
}

function testBuildVariationAssessmentPayload() {
  const questions = [
    quizQuestion({ id: "v1", prompt: "变式一", focus: "概念辨析" }),
    quizQuestion({ id: "v2", prompt: "变式二", focus: "迁移应用" })
  ];
  let state: PracticeState = { ...initialPracticeState(), stage: "answering", bundle: bundleWith(questions) };
  state = recordAnswer(state, questions[0]!, verdict(true, 100), { studentAnswerIndex: 1, studentAnswerText: "" });
  state = recordAnswer(state, questions[1]!, verdict(false, 40), { studentAnswerIndex: 0, studentAnswerText: "" });

  const payload = buildVariationAssessmentPayload({
    courseId: 3,
    studentId: "student-xm",
    item: wrongItem(),
    state
  });

  assertEqual(payload.student_id, "student-xm", "payload student");
  assertEqual(payload.course_id, 3, "payload course");
  assertEqual(payload.knowledge_node_id, "node-1-2", "payload node");
  assertEqual(payload.quiz_answers.length, 2, "payload quiz count");
  assertEqual(payload.quiz_answers[0]!.id, "variation_v1", "payload quiz id");
  assertEqual(payload.quiz_answers[0]!.correct, true, "payload quiz correct");
  assertEqual(payload.quiz_answers[0]!.correct_answer_index, 1, "payload correct index");
  assertEqual(payload.quiz_answers[0]!.selected_answer_index, 1, "payload selected index");
  assertEqual(payload.quiz_answers[1]!.correct, false, "payload second wrong");

  const detail = JSON.parse(payload.detail || "{}") as {
    assessment_type: string;
    variation_practice: { correct: number; weak_focuses: string[] };
    resolved_question_ids?: string[];
  };
  assertEqual(detail.assessment_type, "wrong_question_variation_practice", "detail type");
  assertEqual(detail.variation_practice.correct, 1, "detail correct count");
  assertEqual(detail.variation_practice.weak_focuses, ["迁移应用"], "detail weak focuses");
  // 拓展练习不标记原错题为已解决
  assertEqual(detail.resolved_question_ids, undefined, "no resolved ids");
}

function testShortAnswerRecordKeepsText() {
  const shortQuestion: VariationQuestion = {
    id: "v3",
    question_type: "short_answer",
    prompt: "说清判定规则",
    options: [],
    correct_answer_index: null,
    reference_answer: "规则",
    focus: "表述与自检",
    difficulty: "挑战"
  };
  let state: PracticeState = { ...initialPracticeState(), stage: "answering", bundle: bundleWith([shortQuestion]) };
  state = recordAnswer(state, shortQuestion, verdict(true, 80), { studentAnswerText: "我的回答" });
  assertEqual(state.records[0]!.studentAnswerText, "我的回答", "short answer text kept");

  const payload = buildVariationAssessmentPayload({
    courseId: 1,
    studentId: "s",
    item: wrongItem(),
    state
  });
  assertEqual(payload.quiz_answers[0]!.options?.length ?? -1, 0, "short answer has no options");
  assertEqual(payload.quiz_answers[0]!.correct_answer_index, undefined, "short answer has no correct index");
}

const tests = [
  testBuildTutorContext,
  testPracticeStateFlow,
  testSummarizePractice,
  testBuildVariationAssessmentPayload,
  testShortAnswerRecordKeepsText
];

for (const test of tests) {
  test();
}
console.log(`wrongQuestionTutorModel: ${tests.length} tests passed`);
