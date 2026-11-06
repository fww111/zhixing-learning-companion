import type { CourseLearningPath, CourseLearningStage, KnowledgeGraph, LearningProfileEvent } from "../api/client";
import { buildWrongQuestionBookModel } from "./courseWrongQuestionBookModel";

export type MasteryBucket = "not_started" | "severe_weak" | "basic" | "good" | "proficient";

export interface MasteryStats {
  total: number;
  notStarted: number;
  severeWeak: number;
  basic: number;
  good: number;
  proficient: number;
  /** 达标以上（good + proficient）占比 0-100 */
  masteredPercent: number;
  /** 严重弱项数量（今日学习最需要关注的信号） */
  weakFocusCount: number;
}

export interface StudyStreak {
  /** 从今天（或最近一次学习日）往回的连续学习天数，至少为有记录时 1 */
  days: number;
  /** 最近一次学习事件日期（YYYY-MM-DD），无记录为空 */
  lastActiveDate: string;
}

export interface TodayDashboardModel {
  todayTasks: CourseLearningStage[];
  currentTask?: CourseLearningStage;
  upcomingTasks: CourseLearningStage[];
  mastery: MasteryStats;
  wrongQuestionCount: number;
  resolvedWrongCount: number;
  streak: StudyStreak;
  recentTopics: string[];
  /** 本周（近 7 天）学习事件数 */
  weekEventCount: number;
  pathScheduleSummary: string;
  hasPath: boolean;
}

type GraphRecord = Record<string, unknown>;

const MASTERY_STATUS_ALIASES: Record<string, MasteryBucket> = {
  default: "not_started",
  none: "not_started",
  not_started: "not_started",
  unlearned: "not_started",
  未学习: "not_started",
  weak: "severe_weak",
  severe_weak: "severe_weak",
  severe_weakness: "severe_weak",
  failed: "severe_weak",
  fail: "severe_weak",
  严重弱项: "severe_weak",
  弱项: "severe_weak",
  不达标: "severe_weak",
  basic: "basic",
  foundation: "basic",
  掌握基础: "basic",
  基础: "basic",
  good: "good",
  qualified: "good",
  pass: "good",
  passed: "good",
  达标良好: "good",
  达标: "good",
  良好: "good",
  proficient: "proficient",
  mastery: "proficient",
  mastered: "proficient",
  精通: "proficient"
};

function masteryStatusFromScore(score: number): MasteryBucket {
  if (score < 0.4) {
    return "severe_weak";
  }
  if (score < 0.6) {
    return "basic";
  }
  if (score < 0.9) {
    return "good";
  }
  return "proficient";
}

function nodeMasteryBucket(node: GraphRecord): MasteryBucket {
  const explicit = ["mastery_status", "masteryStatus", "learning_status", "mastery_level"]
    .map((key) => (typeof node[key] === "string" ? (node[key] as string).trim().toLowerCase() : ""))
    .find(Boolean);
  if (explicit) {
    return MASTERY_STATUS_ALIASES[explicit] ?? MASTERY_STATUS_ALIASES[explicit.replace(/\s+/g, "")] ?? "not_started";
  }
  for (const key of ["mastery_score", "masteryScore", "mastery", "score"]) {
    const value = node[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return masteryStatusFromScore(value);
    }
  }
  return "not_started";
}

export function buildMasteryStats(nodes: GraphRecord[]): MasteryStats {
  const counts: Record<MasteryBucket, number> = {
    not_started: 0,
    severe_weak: 0,
    basic: 0,
    good: 0,
    proficient: 0
  };
  for (const node of nodes) {
    counts[nodeMasteryBucket(node)] += 1;
  }
  const mastered = counts.good + counts.proficient;
  return {
    total: nodes.length,
    notStarted: counts.not_started,
    severeWeak: counts.severe_weak,
    basic: counts.basic,
    good: counts.good,
    proficient: counts.proficient,
    masteredPercent: nodes.length ? Math.round((mastered / nodes.length) * 100) : 0,
    weakFocusCount: counts.severe_weak
  };
}

function localDateString(value: string): string {
  return (value || "").slice(0, 10);
}

function daysBetween(left: string, right: string): number {
  const leftTime = Date.parse(`${left}T00:00:00`);
  const rightTime = Date.parse(`${right}T00:00:00`);
  if (Number.isNaN(leftTime) || Number.isNaN(rightTime)) {
    return Number.NaN;
  }
  return Math.round((leftTime - rightTime) / 86_400_000);
}

export function buildStudyStreak(events: LearningProfileEvent[], today = localDateString(new Date().toISOString())): StudyStreak {
  const activeDays = [
    ...new Set(
      events
        .filter((event) => Boolean(event.created_at))
        .map((event) => localDateString(event.created_at))
    )
  ].sort((left, right) => right.localeCompare(left));

  if (!activeDays.length) {
    return { days: 0, lastActiveDate: "" };
  }

  const lastActiveDate = activeDays[0]!;
  // 最近一次学习在 48h 内都视为连续；再往回逐日检查
  let days = 1;
  if (daysBetween(today, lastActiveDate) > 1) {
    return { days: 0, lastActiveDate };
  }
  for (let index = 1; index < activeDays.length; index += 1) {
    const gap = daysBetween(activeDays[index - 1]!, activeDays[index]!);
    if (gap === 1) {
      days += 1;
    } else {
      break;
    }
  }
  return { days, lastActiveDate };
}

export function buildTodayDashboardModel(input: {
  path?: CourseLearningPath;
  graph?: KnowledgeGraph;
  events?: LearningProfileEvent[];
  today?: string;
}): TodayDashboardModel {
  const events = input.events || [];
  const path = input.path;
  const stages = path?.stages || [];

  const todayTasks = stages.filter((stage) => stage.is_today_task);
  const currentTask = stages.find((stage) => stage.is_current) || todayTasks[0] || stages.find((stage) => !stage.is_locked);
  const todayIds = new Set(todayTasks.map((task) => task.node_id));
  const upcomingTasks = stages
    .filter((stage) => !stage.is_locked && !todayIds.has(stage.node_id) && stage.node_id !== currentTask?.node_id)
    .slice(0, 3);

  const wrongBook = buildWrongQuestionBookModel({ events, nodes: input.graph?.nodes || [] });

  const weekEventCount = events.filter((event) => {
    const day = localDateString(event.created_at);
    if (!input.today) {
      return false;
    }
    const gap = daysBetween(input.today, day);
    return Number.isFinite(gap) && gap >= 0 && gap <= 7;
  }).length;

  const recentTopics = [
    ...new Set(
      events
        .filter((event) => event.event_type !== "assessment_submitted")
        .map((event) => event.topic)
        .filter(Boolean)
    )
  ].slice(0, 4);

  return {
    todayTasks,
    currentTask,
    upcomingTasks,
    mastery: buildMasteryStats(input.graph?.nodes || []),
    wrongQuestionCount: wrongBook.summary.unresolved,
    resolvedWrongCount: wrongBook.summary.resolved,
    streak: buildStudyStreak(events, input.today),
    recentTopics,
    weekEventCount,
    pathScheduleSummary: path?.schedule_summary || "",
    hasPath: Boolean(path && stages.length)
  };
}
