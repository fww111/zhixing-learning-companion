import type { StudentProfile } from "../api/client";

export interface ProfileMetric {
  label: string;
  value: string;
  detail: string;
  tone: "green" | "blue" | "amber" | "slate";
}

export interface ProfileRadarAxis {
  label: string;
  score: number;
  description: string;
}

export interface ProfileDimensionCard {
  title: string;
  value: string;
  detail: string;
  score: number;
}

export interface ProfileTagGroup {
  title: string;
  items: string[];
  empty: string;
}

export interface ProfileTimelineItem {
  source: string;
  topic: string;
  detail: string;
}

export interface ProfileVisualizationModel {
  versionLabel: string;
  completionPercent: number;
  confidencePercent: number;
  summary: string;
  metrics: ProfileMetric[];
  radarAxes: ProfileRadarAxis[];
  dimensionCards: ProfileDimensionCard[];
  tagGroups: ProfileTagGroup[];
  modalityRows: Array<{ label: string; detail: string; score: number }>;
  updateReason?: string;
  riskSignals: string[];
  growthSummary?: string;
  timeline: ProfileTimelineItem[];
}

export function buildProfileVisualizationModel(profile: StudentProfile): ProfileVisualizationModel {
  const completionPercent = toPercent(profile.completion_score);
  const confidencePercent = toPercent(profile.confidence_score);
  const codePerformanceScore = scoreFromRecord(profile.code_performance, ["pass_rate", "accuracy", "score"]);
  const codeScore = toPercent(profile.application_ability) || codePerformanceScore || 28;
  const quizScore = scoreFromRecord(profile.quiz_performance, ["accuracy", "avg_score", "score"]) ?? trendLatest(profile.accuracy_trend);
  const resourceFitScore = average([
    modalityAverage(profile),
    scoreFromConfidence(profile, "resource_fit"),
    profile.resource_preference?.length ? 78 : undefined
  ]);
  const strategyScore = average([
    scoreFromConfidence(profile, "learning_strategy"),
    hasText(profile.cognitive_style) ? 76 : undefined,
    hasText(profile.learning_style) ? 76 : undefined
  ]);
  const engagementScore = average([
    toPercent(profile.motivation_level),
    toPercent(profile.persistence_level),
    trendLatest(profile.completion_trend),
    profile.weekly_time_budget_minutes ? Math.min(100, Math.max(35, Math.round(profile.weekly_time_budget_minutes / 4.2))) : undefined
  ]);

  const radarAxes: ProfileRadarAxis[] = [
    {
      label: "知识基础",
      score: scoreFromConfidence(profile, "knowledge_foundation") ?? scoreForText(profile.knowledge_foundation, completionPercent),
      description: valueOrPending(profile.knowledge_foundation)
    },
    {
      label: "代码实践",
      score: codeScore,
      description: compactText([
        formatScoreDetail("应用能力", codeScore),
        typeof codePerformanceScore === "number" ? formatScoreDetail("实操通过率", codePerformanceScore) : undefined
      ])
    },
    {
      label: "学习投入",
      score: engagementScore,
      description: scheduleText(profile)
    },
    {
      label: "认知策略",
      score: strategyScore,
      description: compactText([profile.cognitive_style, profile.learning_style])
    },
    {
      label: "资源适配",
      score: resourceFitScore,
      description: listText(profile.resource_preference?.map(resourceLabel), "待观察资源偏好")
    },
    {
      label: "评估稳定",
      score: quizScore,
      description: compactText([profile.assessment_preference, formatScoreDetail("测验表现", quizScore)])
    }
  ].map((axis) => ({ ...axis, score: clampPercent(axis.score) }));

  const dimensionCards: ProfileDimensionCard[] = [
    {
      title: "基础信息",
      value: `${valueOrPending(profile.major)} / ${valueOrPending(profile.grade)}`,
      detail: "用于判断课程起点与解释粒度",
      score: scoreForValues([profile.major, profile.grade], profile)
    },
    {
      title: "课程目标",
      value: valueOrPending(profile.course_goal || profile.learning_goal),
      detail: "驱动学习路径优先级和资源选择",
      score: scoreForValues([profile.course_goal, profile.learning_goal], profile)
    },
    {
      title: "知识基础",
      value: valueOrPending(profile.knowledge_foundation),
      detail: "决定图谱起始节点和补救任务",
      score: radarAxes[0].score
    },
    {
      title: "认知与策略",
      value: compactText([profile.cognitive_style, profile.learning_style]),
      detail: "影响讲解方式、例题密度和复盘节奏",
      score: strategyScore
    },
    {
      title: "学习时间",
      value: scheduleText(profile),
      detail: "学习路径排期必须遵循此约束",
      score: scoreForValues([profile.time_preference, profile.available_days?.join(","), String(profile.weekly_time_budget_minutes || "")], profile)
    },
    {
      title: "评估偏好",
      value: valueOrPending(profile.assessment_preference),
      detail: "控制测验、编程题和反馈形式",
      score: scoreForValues(profile.assessment_preference, profile)
    }
  ].map((card) => ({ ...card, score: clampPercent(card.score) }));

  const modalityRows = Object.entries(profile.modality_effectiveness || {}).slice(0, 5).map(([name, stats]) => {
    const score = toPercent(stats.avg_score ?? stats.last_score);
    return {
      label: resourceLabel(name),
      detail: `使用 ${stats.uses || 0} 次 · 均分 ${score}%`,
      score
    };
  });

  const risk = profile.learning_risk || {};
  const growth = profile.growth_trend || {};
  const riskSignals = Array.isArray(risk.signals) ? risk.signals.map(String).filter(Boolean).slice(0, 4) : [];
  const masterySamples = Array.isArray(growth.mastery_scores) ? growth.mastery_scores.length : 0;
  const completionSamples = Array.isArray(growth.completion_scores) ? growth.completion_scores.length : 0;

  return {
    versionLabel: `v${profile.profile_version || 1}`,
    completionPercent,
    confidencePercent,
    summary: profile.profile_summary?.trim() || fallbackSummary(profile),
    metrics: [
      { label: "画像完整度", value: `${completionPercent}%`, detail: "核心维度覆盖", tone: "green" },
      { label: "画像置信度", value: `${confidencePercent}%`, detail: "证据可信水平", tone: "blue" },
      { label: "最近事件", value: profile.last_event_id ? `#${profile.last_event_id}` : "暂无", detail: "随学随新触发", tone: "slate" }
    ],
    radarAxes,
    dimensionCards,
    tagGroups: [
      { title: "薄弱点", items: normalizedItems(profile.weak_points, "暂无明显薄弱点"), empty: "暂无明显薄弱点" },
      { title: "优势点", items: normalizedItems(profile.strong_points, "仍在积累证据"), empty: "仍在积累证据" },
      { title: "常见误区", items: normalizedItems(profile.misconception_patterns, "暂无稳定误区"), empty: "暂无稳定误区" },
      { title: "图谱关注", items: normalizedItems(profile.knowledge_graph_focus, "等待学习行为补充"), empty: "等待学习行为补充" },
      { title: "资源偏好", items: normalizedItems(profile.resource_preference?.map(resourceLabel), "待观察资源偏好"), empty: "待观察资源偏好" },
      { title: "约束条件", items: normalizedItems(profile.constraints, "暂无特殊约束"), empty: "暂无特殊约束" }
    ],
    modalityRows,
    updateReason: profile.last_profile_update_reason?.trim() || undefined,
    riskSignals,
    growthSummary: masterySamples || completionSamples
      ? `掌握趋势样本 ${masterySamples} · 完成趋势样本 ${completionSamples} · 风险等级 ${String(risk.level || "normal")}`
      : undefined,
    timeline: (profile.updated_evidence || []).filter(Boolean).slice(-4).reverse()
  };
}

export function resourceLabel(value: string) {
  return {
    code_lab: "编程练习",
    document: "文档笔记",
    exercise: "题库练习",
    mind_map: "思维导图",
    openmaic_classroom: "标准课堂",
    reading: "拓展阅读",
    video: "视频脚本"
  }[value] || value;
}

function toPercent(value: unknown) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return 0;
  }
  return clampPercent(Math.round(value * 100));
}

function clampPercent(value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, Math.round(value)));
}

function average(values: Array<number | undefined>) {
  const numeric = values.filter((value): value is number => typeof value === "number" && !Number.isNaN(value));
  if (!numeric.length) {
    return 28;
  }
  return Math.round(numeric.reduce((sum, value) => sum + value, 0) / numeric.length);
}

function scoreFromConfidence(profile: StudentProfile, key: string) {
  const value = profile.dimension_confidence?.[key];
  return typeof value === "number" ? toPercent(value) : undefined;
}

function scoreFromRecord(record: Record<string, unknown> | undefined, keys: string[]) {
  if (!record) {
    return undefined;
  }
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number") {
      return toPercent(value);
    }
  }
  return undefined;
}

function trendLatest(values: number[] | undefined) {
  const numeric = values?.filter((value) => typeof value === "number" && !Number.isNaN(value));
  const last = numeric?.length ? numeric[numeric.length - 1] : undefined;
  return typeof last === "number" ? toPercent(last) : undefined;
}

function modalityAverage(profile: StudentProfile) {
  const values = Object.values(profile.modality_effectiveness || {})
    .map((stats) => stats.avg_score ?? stats.last_score)
    .filter((value): value is number => typeof value === "number" && !Number.isNaN(value))
    .map(toPercent);
  return values.length ? average(values) : undefined;
}

function scoreForText(value: string | undefined, completionPercent: number) {
  return hasText(value) ? Math.max(62, Math.min(96, completionPercent || 72)) : 18;
}

function scoreForValues(value: string | Array<string | undefined> | undefined, profile: StudentProfile) {
  if (Array.isArray(value)) {
    return value.some(hasText) ? Math.max(62, Math.min(96, toPercent(profile.completion_score) || 72)) : 18;
  }
  return hasText(value) ? Math.max(62, Math.min(96, toPercent(profile.completion_score) || 72)) : 18;
}

function hasText(value: string | undefined) {
  return Boolean(value?.trim());
}

function valueOrPending(value?: string) {
  return value?.trim() || "待补充";
}

function compactText(values: Array<string | undefined>) {
  const items = values.map((item) => item?.trim()).filter(Boolean);
  return items.length ? items.join(" / ") : "待补充";
}

function listText(values: string[] | undefined, fallback: string) {
  const items = values?.filter(Boolean);
  return items?.length ? items.slice(0, 4).join("、") : fallback;
}

function scheduleText(profile: StudentProfile) {
  const days = (profile.available_days || []).filter(Boolean).join("、");
  const weekly = profile.weekly_time_budget_minutes ? `每周 ${profile.weekly_time_budget_minutes} 分钟` : "";
  const daily = profile.daily_time_budget_minutes
    ? Object.entries(profile.daily_time_budget_minutes).slice(0, 3).map(([day, minutes]) => `${day}${minutes}分钟`).join("、")
    : "";
  return compactText([profile.time_preference, days, weekly, daily]);
}

function normalizedItems(values: string[] | undefined, fallback: string) {
  const items = (values || []).map((item) => item?.trim()).filter(Boolean).slice(0, 6);
  return items.length ? items : [fallback];
}

function formatScoreDetail(label: string, score: number | undefined) {
  return typeof score === "number" ? `${label} ${clampPercent(score)}%` : `${label}待观察`;
}

function fallbackSummary(profile: StudentProfile) {
  return `该学生当前目标是${profile.learning_goal || "完成课程学习"}，薄弱点集中在${(profile.weak_points || []).slice(0, 3).join("、") || "待观察"}，适合结合${(profile.resource_preference || []).slice(0, 3).map(resourceLabel).join("、") || "多模态资源"}持续学习。`;
}
