import type { CourseLearningPath, CourseLearningStage, KnowledgeGraph, LearningProfileEvent } from "../api/client.js";
import {
  buildMasteryStats,
  buildStudyStreak,
  buildTodayDashboardModel
} from "./todayDashboardModel.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual<T>(actual: T, expected: T, label: string) {
  const same = Object.is(actual, expected)
    || (typeof actual === "object" && typeof expected === "object" && JSON.stringify(actual) === JSON.stringify(expected));
  if (!same) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)} but got ${JSON.stringify(actual)}`);
  }
}

function stage(overrides: Partial<CourseLearningStage> = {}): CourseLearningStage {
  return {
    node_id: "n1",
    topic: "1.1 变量",
    level: 2,
    order: 1,
    mastery_status: "not_started",
    mastery_score: null,
    priority_score: 0,
    path_status: "open",
    is_current: false,
    is_locked: false,
    is_remedial: false,
    estimated_minutes: 30,
    scheduled_day: "周一",
    scheduled_date: "2026-11-06",
    scheduled_minutes: 30,
    schedule_label: "今日",
    is_today_task: false,
    task_type: "minimum",
    is_minimum_task: true,
    is_stretch_task: false,
    goal: "",
    practice_task: "",
    graph_basis: [],
    profile_basis: [],
    recommended_resource_types: [],
    recommendation_reason: "",
    ...overrides
  };
}

function event(overrides: Partial<LearningProfileEvent> = {}): LearningProfileEvent {
  return {
    id: 1,
    user_id: 1,
    course_id: 1,
    student_profile_id: 1,
    knowledge_node_id: "n1",
    lesson_session_id: null,
    event_type: "lesson_viewed",
    topic: "1.1 变量",
    detail: "",
    event_payload: {},
    evidence_strength: "medium",
    score: null,
    created_at: "2026-11-06T10:00:00",
    ...overrides
  };
}

function testMasteryStats() {
  const stats = buildMasteryStats([
    { id: "a", mastery_status: "未学习" },
    { id: "b", mastery_status: "严重弱项" },
    { id: "c", mastery_status: "掌握基础" },
    { id: "d", mastery_score: 0.75 },
    { id: "e", mastery: 0.95 },
    { id: "f" }
  ]);
  assertEqual(stats.total, 6, "mastery total");
  assertEqual(stats.notStarted, 2, "not started count");
  assertEqual(stats.severeWeak, 1, "severe weak count");
  assertEqual(stats.basic, 1, "basic count");
  assertEqual(stats.good, 1, "good count");
  assertEqual(stats.proficient, 1, "proficient count");
  assertEqual(stats.masteredPercent, 33, "mastered percent");
}

function testStudyStreak() {
  const streak = buildStudyStreak(
    [
      event({ created_at: "2026-11-06T09:00:00" }),
      event({ created_at: "2026-11-05T09:00:00" }),
      event({ created_at: "2026-11-04T09:00:00" }),
      event({ created_at: "2026-11-01T09:00:00" })
    ],
    "2026-11-06"
  );
  assertEqual(streak.days, 3, "streak days");
  assertEqual(streak.lastActiveDate, "2026-11-06", "last active date");

  const stale = buildStudyStreak([event({ created_at: "2026-11-01T09:00:00" })], "2026-11-06");
  assertEqual(stale.days, 0, "stale streak resets");

  const empty = buildStudyStreak([], "2026-11-06");
  assertEqual(empty.days, 0, "empty streak");
}

function testTodayDashboard() {
  const path: CourseLearningPath = {
    student_id: "s",
    course_id: 1,
    plan_type: "main",
    focus_node_id: "n2",
    current_stage_id: "n2",
    pass_threshold: 0.75,
    is_dynamic: true,
    adjustment_basis: [],
    weekly_time_budget_minutes: 300,
    planned_minutes: 60,
    minimum_task_count: 1,
    stretch_task_count: 1,
    schedule_days: ["2026-11-06"],
    schedule_summary: "每天 1 小时",
    active_chapter_id: "c1",
    active_chapter_title: "第1章",
    chapters: [],
    stages: [
      stage({ node_id: "n1", is_today_task: true, is_current: true, topic: "今日任务A" }),
      stage({ node_id: "n2", is_today_task: true, topic: "今日任务B", order: 2 }),
      stage({ node_id: "n3", is_locked: true, order: 3 }),
      stage({ node_id: "n4", order: 4, topic: "解锁后续" })
    ]
  };
  const graph: KnowledgeGraph = {
    nodes: [
      { id: "n1", mastery_status: "达标良好" },
      { id: "n2", mastery_status: "未学习" },
      { id: "n3", mastery_status: "严重弱项" },
      { id: "n4", mastery_status: "未学习" }
    ],
    edges: []
  };
  const events = [
    event({ event_type: "assessment_submitted", topic: "quiz", event_payload: { assessment: { quiz_answers: [{ correct: false }] } } }),
    event({ event_type: "lesson_viewed", topic: "1.2 指针" })
  ];

  const model = buildTodayDashboardModel({ path, graph, events, today: "2026-11-06" });

  assertEqual(model.todayTasks.length, 2, "today tasks count");
  assertEqual(model.currentTask?.node_id, "n1", "current task");
  assertEqual(model.upcomingTasks.length, 1, "upcoming excludes today and locked");
  assertEqual(model.upcomingTasks[0]?.node_id, "n4", "upcoming is unlocked non-today");
  assertEqual(model.mastery.weakFocusCount, 1, "weak focus count");
  assertEqual(model.mastery.masteredPercent, 25, "mastered percent");
  assertEqual(model.wrongQuestionCount, 1, "wrong question unresolved");
  assertEqual(model.streak.days, 1, "streak from today events");
  assertEqual(model.weekEventCount, 2, "week event count");
  assertEqual(model.hasPath, true, "has path");
  assertEqual(model.pathScheduleSummary, "每天 1 小时", "schedule summary");
}

function testEmptyDashboard() {
  const model = buildTodayDashboardModel({ events: [], today: "2026-11-06" });
  assertEqual(model.todayTasks.length, 0, "no tasks");
  assertEqual(model.mastery.total, 0, "no nodes");
  assertEqual(model.mastery.masteredPercent, 0, "empty percent safe");
  assertEqual(model.wrongQuestionCount, 0, "no wrong questions");
  assertEqual(model.hasPath, false, "no path");
  assertEqual(model.streak.days, 0, "no streak");
}

const tests = [testMasteryStats, testStudyStreak, testTodayDashboard, testEmptyDashboard];
for (const test of tests) {
  test();
}
console.log(`todayDashboardModel: ${tests.length} tests passed`);
