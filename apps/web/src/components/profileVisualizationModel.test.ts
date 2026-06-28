import type { StudentProfile } from "../api/client.js";
import { buildProfileVisualizationModel } from "./profileVisualizationModel.js";

function assert(condition: boolean, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, got ${String(actual)}`);
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

const profile: StudentProfile = {
  student_id: "student-1",
  major: "计算机科学",
  grade: "大一",
  learning_goal: "掌握 Python 程序设计",
  course_goal: "完成 Python 程序设计课程",
  profile_summary: "目标明确，适合用代码实操和思维导图推进。",
  profile_version: 3,
  last_event_id: 17,
  last_profile_update_reason: "代码练习通过率提升，更新实践能力画像。",
  dimension_confidence: {
    knowledge_foundation: 0.62,
    learning_strategy: 0.78,
    resource_fit: 0.84
  },
  knowledge_foundation: "具备变量和条件语句基础",
  learning_style: "任务驱动",
  cognitive_style: "先看示例再归纳规则",
  weak_points: ["函数参数", "循环嵌套"],
  strong_points: ["课堂完成度稳定"],
  misconception_patterns: ["容易混淆形参与实参"],
  time_preference: "每天1小时",
  available_days: ["周一", "周二", "周三", "周四", "周五"],
  weekly_time_budget_minutes: 300,
  daily_time_budget_minutes: { "周一": 60, "周二": 60 },
  resource_preference: ["code_lab", "mind_map", "document"],
  modality_effectiveness: {
    code_lab: { uses: 4, avg_score: 0.86 },
    mind_map: { uses: 2, avg_score: 0.74 }
  },
  preferred_resource_order: ["code_lab", "mind_map", "document"],
  motivation: "希望提升编程能力",
  motivation_level: 0.8,
  persistence_level: 0.7,
  constraints: ["课后时间有限"],
  assessment_preference: "短测验 + 编程题",
  quiz_performance: { accuracy: 0.72 },
  code_performance: { pass_rate: 0.68 },
  application_ability: 0.66,
  accuracy_trend: [0.5, 0.66, 0.72],
  completion_trend: [0.7, 0.8],
  affective_state: { confidence: "medium" },
  learning_risk: { level: "watch", signals: ["函数题波动"] },
  growth_trend: { mastery_scores: [0.48, 0.62], completion_scores: [0.75, 0.82] },
  knowledge_graph_focus: ["函数基础", "循环结构"],
  confidence_score: 0.9,
  completion_score: 1,
  updated_evidence: [
    { source: "assessment", topic: "函数", detail: "函数参数题得分偏低" },
    { source: "classroom", topic: "循环", detail: "完成课堂测试" }
  ]
};

test("builds a visual profile model from multi-dimensional student profile data", () => {
  const model = buildProfileVisualizationModel(profile);

  assertEqual(model.versionLabel, "v3", "version should match profile version");
  assertEqual(model.completionPercent, 100, "completion score should be formatted as percent");
  assertEqual(model.confidencePercent, 90, "confidence score should be formatted as percent");
  assertEqual(model.summary, "目标明确，适合用代码实操和思维导图推进。", "summary should use stored profile summary");
  assertEqual(model.radarAxes.length, 6, "radar should expose six profile axes");
  assert(model.radarAxes.every((axis) => axis.score >= 12 && axis.score <= 100), "radar scores should stay in the visual range");
  assert(model.radarAxes.some((axis) => axis.label === "代码实践" && axis.score === 66), "code practice axis should use application ability");
  assert(model.dimensionCards.some((card) => card.title === "学习时间" && card.value.includes("每周 300 分钟")), "time card should include weekly budget");
  assert(model.tagGroups.some((group) => group.title === "薄弱点" && group.items.includes("函数参数")), "weak points should be shown as tags");
  assert(model.timeline[0].topic === "循环", "latest profile evidence should be shown first");
});

test("uses stable fallback labels when profile fields are incomplete", () => {
  const model = buildProfileVisualizationModel({
    ...profile,
    profile_summary: undefined,
    major: "",
    grade: "",
    weak_points: [],
    resource_preference: [],
    completion_score: 1.4,
    confidence_score: -0.2,
    updated_evidence: []
  });

  assertEqual(model.completionPercent, 100, "completion percent should be clamped");
  assertEqual(model.confidencePercent, 0, "confidence percent should be clamped");
  assert(model.summary.includes("掌握 Python 程序设计"), "fallback summary should include the learning goal");
  assert(model.dimensionCards.some((card) => card.title === "基础信息" && card.value.includes("待补充")), "missing major and grade should show pending text");
  assert(model.tagGroups.some((group) => group.title === "薄弱点" && group.items[0] === "暂无明显薄弱点"), "empty weak points should show a stable fallback tag");
  assertEqual(model.timeline.length, 0, "empty evidence should not render timeline items");
});
