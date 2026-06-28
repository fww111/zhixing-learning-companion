import { buildCourseAssessmentDashboardModel } from "./courseAssessmentDashboardModel.js";
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

const nodes: Array<Record<string, unknown>> = [
  { id: "chapter-1", name: "第 1 章", type: "chapter" },
  { id: "n1", name: "变量与输入输出", type: "knowledge", mastery_status: "basic", mastery_score: 0.68 },
  { id: "n2", name: "条件分支", type: "knowledge", mastery_status: "good", mastery_score: 0.82 },
  { id: "n3", name: "循环结构", type: "knowledge", mastery_status: "not_started" }
];

const events: LearningProfileEvent[] = [
  {
    id: 12,
    user_id: 1,
    course_id: 41,
    student_profile_id: 7,
    knowledge_node_id: "n1",
    event_type: "assessment_submitted",
    topic: "变量与输入输出",
    detail: "变量综合评估",
    event_payload: {
      assessment: {
        topic: "变量与输入输出",
        quiz_answers: [
          {
            id: "concept",
            dimension: "概念理解",
            prompt: "在 Python 中，下列哪个变量名是不合法的？",
            options: ["_my_var", "2nd_value", "userName", "PI"],
            correct_answer_index: 1,
            selected_answer_index: 0,
            correct: false,
            weight: 0.35
          },
          {
            id: "transfer",
            dimension: "迁移应用",
            prompt: "input() 返回什么类型？",
            options: ["int", "str", "bool"],
            correct_answer_index: 1,
            selected_answer_index: 1,
            correct: true,
            weight: 0.3
          }
        ],
        code_attempt: {
          prompt: "编写变量交换程序。",
          code: "num1 = input()",
          expected_output: "交换前：num1=3, num2=8\n交换后：num1=8, num2=3",
          actual_output: "3 8",
          passed: false,
          attempts: 2
        }
      },
      final_score: 0.58,
      passed: false,
      dimension_scores: {
        classroom: 1,
        quiz: 0.65,
        code: 0.25,
        behavior: 0.67
      }
    },
    evidence_strength: "strong",
    score: 0.58,
    created_at: "2026-06-07T10:00:00Z"
  }
];

test("assessment dashboard exposes multidimensional visual metrics without profile content", () => {
  const model = buildCourseAssessmentDashboardModel({ events, nodes });

  assert(model.summary.totalLearningNodes === 3, "chapter nodes should not count as learning tasks");
  assert(model.summary.assessedNodes === 2, "assessed nodes should exclude not started nodes");
  assert(model.summary.passedNodes === 1, "only good/proficient nodes should count as passed");
  assert(model.dimensionCards.length >= 5, "dashboard should expose multiple assessment dimensions");
  assert(model.dimensionCards.some((card) => card.key === "quiz" && card.score === 65), "quiz score should come from assessment events");
  assert(model.dimensionCards.some((card) => card.key === "code" && card.score === 25), "code score should come from assessment events");
  assert(!model.rightRailSections.some((section) => section.key === "student_profile"), "assessment right rail must not render student profile");
});

test("wrong-question collection includes missed quiz items and failed code attempts from lesson assessments", () => {
  const model = buildCourseAssessmentDashboardModel({ events, nodes });

  assert(model.wrongQuestions.length === 2, `expected one quiz wrong item and one code wrong item, got ${model.wrongQuestions.length}`);
  const quizWrong = model.wrongQuestions.find((item) => item.type === "quiz");
  const codeWrong = model.wrongQuestions.find((item) => item.type === "code");

  assert(Boolean(quizWrong), "missed quiz question should be listed");
  assert(Boolean(quizWrong?.prompt.includes("变量名")), "wrong quiz should keep the original professional prompt");
  assert(quizWrong?.selectedAnswer === "_my_var", "wrong quiz should show the learner selected option");
  assert(quizWrong?.correctAnswer === "2nd_value", "wrong quiz should show the correct answer");
  assert(Boolean(codeWrong), "failed programming attempt should be listed");
  assert(Boolean(codeWrong?.prompt.includes("变量交换")), "failed code challenge should keep its prompt");
  assert(codeWrong?.attempts === 2, "failed code attempt count should be preserved");
});
