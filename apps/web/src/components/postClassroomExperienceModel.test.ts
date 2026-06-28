import {
  isInlineCodeRunSuccessful,
  isOpenMAICQuizEvent,
  lessonStageLabel,
  lessonViewModeFromState,
  learningFlowSteps,
  nextPostClassroomStage,
  openmaicClassroomIframeAllow,
  runInlinePythonLikeCode,
  shouldOpenAssessmentForOpenMAICQuizEvent,
  shouldUnlockPostClassroom
} from "./postClassroomExperienceModel.js";

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

test("post classroom flow advances from artifacts to quiz to dynamic assessment", () => {
  assert(nextPostClassroomStage("study_artifacts") === "quiz_lab", "artifacts should advance to quiz lab");
  assert(nextPostClassroomStage("quiz_lab") === "assessment", "quiz lab should advance to assessment");
  assert(nextPostClassroomStage("assessment") === "assessment", "assessment should be terminal");
});

test("learning flow exposes the contest multi-agent loop", () => {
  const labels = learningFlowSteps.map((step) => step.label).join(" -> ");
  assert(labels === "课程学习 -> 文档笔记/思维导图 -> 题库测试/代码运行 -> 评估反馈/动态规划", labels);
});

test("OpenMAIC success unlocks post classroom interactions", () => {
  assert(shouldUnlockPostClassroom("succeeded", "", ""), "succeeded status should unlock");
  assert(shouldUnlockPostClassroom("completed", "", ""), "completed status should unlock");
  assert(shouldUnlockPostClassroom("queued", "http://127.0.0.1:3000/classroom/demo", ""), "url should unlock");
  assert(!shouldUnlockPostClassroom("queued", "", ""), "queued without classroom should stay locked");
});

test("OpenMAIC classroom iframe policy allows embedded fullscreen controls", () => {
  assert(openmaicClassroomIframeAllow.includes("fullscreen"), "classroom iframe must allow fullscreen requests");
  assert(openmaicClassroomIframeAllow.includes("autoplay"), "classroom iframe should keep generated lesson media playable");
});

test("OpenMAIC quiz postMessage events are recognized by the host learning page", () => {
  assert(isOpenMAICQuizEvent({ type: "openmaic:quiz-started", sceneId: "quiz-1" }), "quiz start event should be accepted");
  assert(isOpenMAICQuizEvent({ type: "openmaic:quiz-submitted", score: 80 }), "quiz submit event should be accepted");
  assert(isOpenMAICQuizEvent({ type: "openmaic:quiz-completed", score: 80 }), "quiz completion event should be accepted");
  assert(!isOpenMAICQuizEvent({ type: "openmaic:scene-clicked" }), "unrelated classroom events must not open assessment");
  assert(!isOpenMAICQuizEvent("openmaic:quiz-started"), "plain strings should not be treated as trusted events");
});

test("host keeps OpenMAIC quiz visible until the classroom quiz is completed", () => {
  assert(!shouldOpenAssessmentForOpenMAICQuizEvent("openmaic:quiz-started"), "starting quiz should keep the OpenMAIC quiz visible");
  assert(!shouldOpenAssessmentForOpenMAICQuizEvent("openmaic:quiz-submitted"), "submitted quiz should keep the OpenMAIC review visible");
  assert(shouldOpenAssessmentForOpenMAICQuizEvent("openmaic:quiz-completed"), "completed quiz should open the host assessment panel");
  assert(shouldOpenAssessmentForOpenMAICQuizEvent("pla:open-assessment"), "explicit host assessment events should still open assessment");
});

test("persisted lesson state restores classroom and assessment views", () => {
  assert(lessonViewModeFromState({ current_stage: "classroom" }) === "learn", "classroom stage should open learning view");
  assert(lessonViewModeFromState({ current_stage: "test" }) === "assess", "test stage should open assessment view");
  assert(lessonViewModeFromState({ test_completed: true }) === "assess", "completed test should open assessment view");
  assert(lessonStageLabel({ classroom_completed: true }) === "课堂已完成", "classroom completion should be visible");
  assert(lessonStageLabel({ assessment_completed: true }) === "评估完成", "assessment completion should be visible");
});


test("inline Python-like runner supports variables, print and simple addition", () => {
  const output = runInlinePythonLikeCode([
    "name = 'Python'",
    "score = 40 + 2",
    "print('Hello ' + name)",
    "print(score)"
  ].join("\n"));

  assert(output === "Hello Python\n42", `unexpected output: ${output}`);
  assert(isInlineCodeRunSuccessful(output), "successful output should be ready for assessment");
  assert(!isInlineCodeRunSuccessful("暂不支持的语句：for i in range(3):"), "unsupported syntax should not auto-advance");
});

test("inline Python-like runner supports f-strings used by generated code labs", () => {
  const output = runInlinePythonLikeCode([
    "name = 'Python'",
    "print(f'Hello {name}')"
  ].join("\n"));

  assert(output === "Hello Python", `unexpected output: ${output}`);
});

test("inline Python-like runner supports input, int conversion and tuple swap", () => {
  const output = runInlinePythonLikeCode([
    "num1 = int(input())",
    "num2 = int(input())",
    "print(f'交换前：num1={num1}, num2={num2}')",
    "num1, num2 = num2, num1",
    "print(f'交换后：num1={num1}, num2={num2}')"
  ].join("\n"));

  assert(output === "交换前：num1=3, num2=8\n交换后：num1=8, num2=3", `unexpected input/swap output: ${output}`);
  assert(isInlineCodeRunSuccessful(output), "input-based variable swap should be accepted for assessment");
});

test("inline Python-like runner supports simple range accumulation", () => {
  const output = runInlinePythonLikeCode([
    "n = int(input())",
    "total = 0",
    "for i in range(1, n + 1):",
    "    total = total + i",
    "print(total)"
  ].join("\n"));

  assert(output === "15", `unexpected range sum output: ${output}`);
});

test("inline runner supports simple C printf assessment snippets", () => {
  const output = runInlinePythonLikeCode([
    "#include <stdio.h>",
    "int main() {",
    "printf(\"C语言程序设计 达标\\n\");",
    "return 0;",
    "}"
  ].join("\n"));

  assert(output === "C语言程序设计 达标", `unexpected C output: ${output}`);
  assert(isInlineCodeRunSuccessful(output), "simple printf output should be accepted");
});
