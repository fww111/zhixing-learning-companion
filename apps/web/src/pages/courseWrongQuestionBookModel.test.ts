import {
  buildRedoAssessmentPayload,
  buildWrongQuestionBookModel,
  evaluateWrongQuestionRedo
} from "./courseWrongQuestionBookModel.js";
import type { LearningProfileEvent } from "../api/client.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

const graphNodes: Array<Record<string, unknown>> = [
  { id: "chapter-1", name: "第 1 章 Python 概述", node_type: "chapter" },
  { id: "section-1-1", name: "1.1 初识 Python", node_type: "section", parent_id: "chapter-1" },
  { id: "node-variable", name: "1.1.1 变量与输入输出", node_type: "concept", parent_id: "section-1-1" },
  { id: "chapter-2", name: "第 2 章 程序控制", node_type: "chapter" },
  { id: "node-branch", name: "2.1.1 条件分支", node_type: "concept", parent_id: "chapter-2" }
];

const failedEvent: LearningProfileEvent = {
  id: 12,
  user_id: 1,
  course_id: 41,
  student_profile_id: 7,
  knowledge_node_id: "node-variable",
  event_type: "assessment_submitted",
  topic: "变量与输入输出",
  detail: "变量综合评估",
  event_payload: {
    assessment: {
      topic: "变量与输入输出",
      quiz_answers: [
        {
          id: "agent_question_1",
          dimension: "概念理解",
          prompt: "在 Python 中，下列哪个变量名是不合法的？",
          options: ["_my_var", "2nd_value", "userName", "PI"],
          correct_answer_index: 1,
          selected_answer_index: 0,
          correct: false,
          weight: 0.35
        }
      ],
      code_attempt: {
        prompt: "变量交换与输入输出",
        code: "num1 = input()",
        expected_output: "交换前：num1=3, num2=8\n交换后：num1=8, num2=3",
        actual_output: "3 8",
        passed: false,
        attempts: 2
      }
    },
    final_score: 0.58,
    passed: false
  },
  evidence_strength: "strong",
  score: 0.58,
  created_at: "2026-06-07T10:00:00Z"
};

const resolvedEvent: LearningProfileEvent = {
  ...failedEvent,
  id: 20,
  detail: "错题重做通过",
  event_payload: {
    assessment: {
      topic: "变量与输入输出",
      quiz_answers: [
        {
          id: "agent_question_1",
          dimension: "错题重做",
          prompt: "在 Python 中，下列哪个变量名是不合法的？",
          options: ["_my_var", "2nd_value", "userName", "PI"],
          correct_answer_index: 1,
          selected_answer_index: 1,
          correct: true,
          weight: 1
        }
      ],
      code_attempt: {
        prompt: "变量交换与输入输出",
        code: "num1 = int(input())\nnum2 = int(input())\nprint(f'交换前：num1={num1}, num2={num2}')\nnum1, num2 = num2, num1\nprint(f'交换后：num1={num1}, num2={num2}')",
        expected_output: "交换前：num1=3, num2=8\n交换后：num1=8, num2=3",
        actual_output: "交换前：num1=3, num2=8\n交换后：num1=8, num2=3",
        passed: true,
        attempts: 1
      }
    },
    wrong_question_redo: {
      resolved_question_ids: ["12-quiz-agent_question_1", "12-code"]
    },
    final_score: 0.95,
    passed: true
  },
  score: 0.95,
  created_at: "2026-06-07T11:00:00Z"
};

test("wrong-question book groups unresolved wrong questions by graph chapter", () => {
  const model = buildWrongQuestionBookModel({
    events: [failedEvent],
    nodes: graphNodes
  });

  assert(model.summary.total === 2, `expected 2 wrong questions, got ${model.summary.total}`);
  assert(model.summary.unresolved === 2, `expected 2 unresolved questions, got ${model.summary.unresolved}`);
  assert(model.chapterGroups.length === 1, `expected one chapter group, got ${model.chapterGroups.length}`);
  assert(model.chapterGroups[0].chapterTitle === "第 1 章 Python 概述", model.chapterGroups[0].chapterTitle);
  assert(model.chapterGroups[0].sections[0].sectionTitle === "1.1 初识 Python", model.chapterGroups[0].sections[0].sectionTitle);
  assert(model.chapterGroups[0].sections[0].items[0].options?.length === 4, "quiz options should be preserved for redo");
});

test("wrong-question book marks previously corrected questions as resolved", () => {
  const model = buildWrongQuestionBookModel({
    events: [failedEvent, resolvedEvent],
    nodes: graphNodes
  });

  assert(model.summary.total === 2, "resolved questions should remain visible as history");
  assert(model.summary.unresolved === 0, "resolved questions should not count as pending");
  assert(model.chapterGroups[0].sections[0].items.every((item) => item.resolved), "all source wrong questions should be resolved");
});

test("wrong-question redo validates quiz choices and code output", () => {
  const model = buildWrongQuestionBookModel({ events: [failedEvent], nodes: graphNodes });
  const quiz = model.chapterGroups[0].sections[0].items.find((item) => item.type === "quiz");
  const code = model.chapterGroups[0].sections[0].items.find((item) => item.type === "code");

  assert(Boolean(quiz && code), "test fixtures should include quiz and code wrong questions");
  assert(evaluateWrongQuestionRedo(quiz!, { selectedAnswerIndex: 1 }).passed, "choosing the correct quiz option should pass");
  assert(!evaluateWrongQuestionRedo(quiz!, { selectedAnswerIndex: 0 }).passed, "choosing the original wrong option should fail");
  assert(evaluateWrongQuestionRedo(code!, {
    code: "print('交换前：num1=3, num2=8')\nprint('交换后：num1=8, num2=3')",
    actualOutput: "交换前：num1=3, num2=8\n交换后：num1=8, num2=3",
    attempts: 1
  }).passed, "matching code output should pass");
});

test("wrong-question redo builds a comprehensive assessment payload for score update", () => {
  const model = buildWrongQuestionBookModel({ events: [failedEvent], nodes: graphNodes });
  const quiz = model.chapterGroups[0].sections[0].items.find((item) => item.type === "quiz");
  assert(Boolean(quiz), "quiz wrong question should exist");

  const payload = buildRedoAssessmentPayload({
    item: quiz!,
    redo: { selectedAnswerIndex: 1 },
    courseId: 41,
    studentId: "student-xm"
  });

  assert(payload.course_id === 41, "payload should keep course scope");
  assert(payload.knowledge_node_id === "node-variable", "payload should target original knowledge node");
  assert(payload.quiz_answers[0].correct_answer_index === 1, "payload should preserve correct answer index");
  assert(payload.quiz_answers[0].selected_answer_index === 1, "payload should submit selected answer");
  assert(payload.quiz_answers[0].correct === true, "payload should mark redo answer correct");
  assert(payload.code_attempt?.passed === true, "quiz redo should include a neutral passed code attempt so existing comprehensive scoring can update the node");
});
