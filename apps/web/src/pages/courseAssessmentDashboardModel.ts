import type { LearningProfileEvent } from "../api/client";

export interface AssessmentDashboardNode {
  id: string;
  name: string;
  summary: string;
  masteryStatus: string;
  masteryScore?: number;
}

export interface AssessmentSummary {
  totalLearningNodes: number;
  assessedNodes: number;
  passedNodes: number;
  weakNodes: number;
  latestScore: number;
}

export interface AssessmentDimensionCard {
  key: string;
  label: string;
  score: number;
  detail: string;
  tone: "green" | "blue" | "amber" | "red" | "slate";
}

export interface WrongQuestionItem {
  id: string;
  type: "quiz" | "code";
  topic: string;
  nodeId: string;
  dimension: string;
  prompt: string;
  selectedAnswer: string;
  correctAnswer: string;
  actualOutput?: string;
  expectedOutput?: string;
  attempts?: number;
  createdAt: string;
}

export interface AssessmentRightRailSection {
  key: string;
  title: string;
}

export interface CourseAssessmentDashboardModel {
  summary: AssessmentSummary;
  masteryCounts: Record<string, number>;
  weakNodeCards: AssessmentDashboardNode[];
  recentNodeCards: AssessmentDashboardNode[];
  dimensionCards: AssessmentDimensionCard[];
  wrongQuestions: WrongQuestionItem[];
  rightRailSections: AssessmentRightRailSection[];
}

const passedStatuses = new Set(["good", "proficient"]);
const weakStatuses = new Set(["severe_weak", "basic"]);

export function buildCourseAssessmentDashboardModel(input: {
  events?: LearningProfileEvent[];
  nodes?: Array<Record<string, unknown>>;
}): CourseAssessmentDashboardModel {
  const learningNodeRecords = learningNodes(input.nodes || []);
  const assessedNodeRecords = learningNodeRecords.filter((node) => masteryStatus(node) !== "not_started");
  const passedNodeRecords = learningNodeRecords.filter((node) => passedStatuses.has(masteryStatus(node)));
  const weakNodeRecords = learningNodeRecords.filter((node) => weakStatuses.has(masteryStatus(node)));
  const latestAssessmentEvent = latestEvent(input.events || []);
  const latestDimensionScores = dimensionScores(latestAssessmentEvent);
  const latestScore = percent(latestAssessmentEvent?.score ?? numberValue(latestAssessmentEvent?.event_payload, "final_score"));

  return {
    summary: {
      totalLearningNodes: learningNodeRecords.length,
      assessedNodes: assessedNodeRecords.length,
      passedNodes: passedNodeRecords.length,
      weakNodes: weakNodeRecords.length,
      latestScore
    },
    masteryCounts: countByMastery(learningNodeRecords),
    weakNodeCards: weakNodeRecords.slice(0, 6).map(toDashboardNode),
    recentNodeCards: [...assessedNodeRecords]
      .sort((left, right) => (masteryScore(right) ?? -1) - (masteryScore(left) ?? -1))
      .slice(0, 6)
      .map(toDashboardNode),
    dimensionCards: buildDimensionCards({
      assessedCount: assessedNodeRecords.length,
      latestDimensionScores,
      passedCount: passedNodeRecords.length,
      totalCount: learningNodeRecords.length,
      weakCount: weakNodeRecords.length
    }),
    wrongQuestions: buildWrongQuestions(input.events || []),
    rightRailSections: [
      { key: "dimension_overview", title: "多维评估" },
      { key: "wrong_question_book", title: "错题集" },
      { key: "closed_loop_rules", title: "闭环规则" }
    ]
  };
}

export function learningNodes(nodes: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  return nodes.filter((node) => {
    const type = textValue(node, "type", textValue(node, "node_type", ""));
    return !["chapter", "section"].includes(type.toLowerCase());
  });
}

export function textValue(record: Record<string, unknown> | undefined, key: string, fallback = ""): string {
  const value = record?.[key];
  return typeof value === "string" ? value : fallback;
}

export function numberValue(record: Record<string, unknown> | undefined, key: string): number | undefined {
  const value = record?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export function masteryStatus(node: Record<string, unknown>): string {
  return textValue(node, "mastery_status", textValue(node, "masteryStatus", "not_started"));
}

export function masteryScore(node: Record<string, unknown>): number | undefined {
  return numberValue(node, "mastery_score") ?? numberValue(node, "masteryScore");
}

function countByMastery(nodes: Array<Record<string, unknown>>) {
  return nodes.reduce<Record<string, number>>((acc, node) => {
    const status = masteryStatus(node);
    acc[status] = (acc[status] ?? 0) + 1;
    return acc;
  }, {});
}

function buildDimensionCards(input: {
  assessedCount: number;
  latestDimensionScores: Record<string, number>;
  passedCount: number;
  totalCount: number;
  weakCount: number;
}): AssessmentDimensionCard[] {
  const passRate = input.totalCount ? input.passedCount / input.totalCount : 0;
  const weakControl = input.totalCount ? 1 - input.weakCount / input.totalCount : 0;
  const assessmentCoverage = input.totalCount ? input.assessedCount / input.totalCount : 0;
  return [
    dimensionCard("classroom", "课堂完成", input.latestDimensionScores.classroom ?? 0, "OpenMAIC 课堂学习完成度"),
    dimensionCard("quiz", "题库测验", input.latestDimensionScores.quiz ?? 0, "选择题/专业题库掌握情况"),
    dimensionCard("code", "编程实践", input.latestDimensionScores.code ?? 0, "浏览器代码运行与输出匹配"),
    dimensionCard("behavior", "学习行为", input.latestDimensionScores.behavior ?? 0, "笔记、导图、代码练习完成证据"),
    dimensionCard("mastery", "图谱达标", passRate, "达标良好/精通知识点占比"),
    dimensionCard("remedial", "薄弱修复", weakControl, "严重弱项和基础掌握节点控制情况"),
    dimensionCard("coverage", "评估覆盖", assessmentCoverage, "已完成评估的知识点比例")
  ];
}

function dimensionCard(key: string, label: string, rawScore: number, detail: string): AssessmentDimensionCard {
  const score = percent(rawScore);
  return {
    key,
    label,
    score,
    detail,
    tone: score >= 85 ? "green" : score >= 75 ? "blue" : score >= 60 ? "amber" : score > 0 ? "red" : "slate"
  };
}

function buildWrongQuestions(events: LearningProfileEvent[]): WrongQuestionItem[] {
  return events
    .filter((event) => event.event_type === "assessment_submitted")
    .flatMap((event) => {
      const payload = objectValue(event.event_payload);
      const assessment = objectValue(payload.assessment) || payload;
      const quizAnswers = arrayValue(assessment.quiz_answers);
      const codeAttempt = objectValue(assessment.code_attempt) || objectValue(payload.code_attempt);
      const quizWrong = quizAnswers
        .filter((answer) => !booleanValue(answer.correct))
        .map((answer, index) => wrongQuizItem(event, answer, index));
      const codeWrong = codeAttempt && !booleanValue(codeAttempt.passed) ? [wrongCodeItem(event, codeAttempt)] : [];
      return [...quizWrong, ...codeWrong];
    })
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

function wrongQuizItem(event: LearningProfileEvent, answer: Record<string, unknown>, index: number): WrongQuestionItem {
  const options = stringArrayValue(answer.options);
  const selectedIndex = integerValue(answer.selected_answer_index);
  const correctIndex = integerValue(answer.correct_answer_index);
  return {
    id: `${event.id}-quiz-${textValue(answer, "id", String(index))}`,
    type: "quiz",
    topic: event.topic,
    nodeId: event.knowledge_node_id,
    dimension: textValue(answer, "dimension", "选择题"),
    prompt: textValue(answer, "prompt", `${event.topic} · ${textValue(answer, "dimension", "选择题")}错题`),
    selectedAnswer: optionLabel(options, selectedIndex, "未作答"),
    correctAnswer: optionLabel(options, correctIndex, "待查看正确答案"),
    createdAt: event.created_at
  };
}

function wrongCodeItem(event: LearningProfileEvent, attempt: Record<string, unknown>): WrongQuestionItem {
  return {
    id: `${event.id}-code`,
    type: "code",
    topic: event.topic,
    nodeId: event.knowledge_node_id,
    dimension: "编程题",
    prompt: textValue(attempt, "prompt", `${event.topic} 编程题`),
    selectedAnswer: "代码输出未匹配预期",
    correctAnswer: "运行输出需要与题目预期一致",
    actualOutput: textValue(attempt, "actual_output"),
    expectedOutput: textValue(attempt, "expected_output"),
    attempts: integerValue(attempt.attempts) ?? 1,
    createdAt: event.created_at
  };
}

function latestEvent(events: LearningProfileEvent[]): LearningProfileEvent | undefined {
  return [...events]
    .filter((event) => event.event_type === "assessment_submitted")
    .sort((left, right) => right.created_at.localeCompare(left.created_at))[0];
}

function dimensionScores(event: LearningProfileEvent | undefined): Record<string, number> {
  const payload = objectValue(event?.event_payload);
  const scores = objectValue(payload.dimension_scores);
  return Object.fromEntries(Object.entries(scores).filter(([, value]) => typeof value === "number")) as Record<string, number>;
}

function toDashboardNode(node: Record<string, unknown>): AssessmentDashboardNode {
  return {
    id: textValue(node, "id"),
    name: textValue(node, "name", textValue(node, "label", "知识点")),
    summary: textValue(node, "summary", "评估记录已写回知识图谱，后续学习路径会按掌握状态动态调整。"),
    masteryStatus: masteryStatus(node),
    masteryScore: masteryScore(node)
  };
}

function percent(score: number | undefined): number {
  if (score === undefined || !Number.isFinite(score)) {
    return 0;
  }
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function arrayValue(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") as Array<Record<string, unknown>> : [];
}

function stringArrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function booleanValue(value: unknown): boolean {
  return value === true;
}

function integerValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) ? value : undefined;
}

function optionLabel(options: string[], index: number | undefined, fallback: string): string {
  if (index === undefined) {
    return fallback;
  }
  return options[index] || `第 ${index + 1} 项`;
}
