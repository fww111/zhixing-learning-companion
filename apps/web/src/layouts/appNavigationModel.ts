export type AppNavKey =
  | "today"
  | "courses"
  | "profile"
  | "graph"
  | "learning_path"
  | "assessment"
  | "wrong_questions"
  | "tutor_stage";

/** 学生旅程视角的导航分组：学习（每天做什么）→ 成长（学得怎么样）→ 课程（资料管理）。 */
export interface AppNavGroup {
  key: "learning" | "growth" | "course";
  label: string;
  items: AppNavKey[];
}

export const appNavGroups: AppNavGroup[] = [
  { key: "learning", label: "学习", items: ["today", "learning_path", "graph", "tutor_stage"] },
  { key: "growth", label: "成长", items: ["profile", "assessment", "wrong_questions"] },
  { key: "course", label: "课程", items: ["courses"] }
];

export const appNavOrder: AppNavKey[] = appNavGroups.flatMap((group) => group.items);

export function navItemState(
  key: AppNavKey,
  pathname: string,
  _search: string,
  disabled = false
): "" | "active" | "disabled" {
  if (disabled) {
    return "disabled";
  }

  if (key === "today") {
    return /^\/courses\/\d+\/today\/?$/.test(pathname) ? "active" : "";
  }

  if (key === "learning_path") {
    return /^\/courses\/\d+\/learning-path\/?$/.test(pathname) ? "active" : "";
  }

  if (key === "assessment") {
    // 学习评估 + 其子页（错题集单独命中，避免双高亮）
    if (/^\/courses\/\d+\/assessment\/wrong-questions\/?$/.test(pathname)) {
      return "";
    }
    return /^\/courses\/\d+\/assessment(?:\/.*)?$/.test(pathname) ? "active" : "";
  }

  if (key === "wrong_questions") {
    return /^\/courses\/\d+\/assessment\/wrong-questions\/?$/.test(pathname) ? "active" : "";
  }

  if (key === "graph") {
    return /^\/courses\/\d+\/graph\/?$/.test(pathname) ? "active" : "";
  }

  if (key === "tutor_stage") {
    return /^\/courses\/\d+\/tutor-stage\/?$/.test(pathname) ? "active" : "";
  }

  if (key === "courses") {
    return pathname === "/courses" || /^\/courses\/\d+\/knowledge-base\/?$/.test(pathname) ? "active" : "";
  }

  return pathname === "/profile/interview" || /^\/courses\/\d+\/profile\/interview\/?$/.test(pathname) ? "active" : "";
}
