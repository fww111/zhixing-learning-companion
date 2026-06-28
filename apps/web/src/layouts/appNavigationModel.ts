export type AppNavKey = "profile" | "courses" | "graph" | "learning_path" | "assessment";

export const appNavOrder: AppNavKey[] = ["courses", "profile", "graph", "learning_path", "assessment"];

export function navItemState(
  key: AppNavKey,
  pathname: string,
  _search: string,
  disabled = false
): "" | "active" | "disabled" {
  if (disabled) {
    return "disabled";
  }

  if (key === "learning_path") {
    return /^\/courses\/\d+\/learning-path\/?$/.test(pathname) ? "active" : "";
  }

  if (key === "assessment") {
    return /^\/courses\/\d+\/assessment(?:\/.*)?$/.test(pathname) ? "active" : "";
  }

  if (key === "graph") {
    return /^\/courses\/\d+\/graph\/?$/.test(pathname) ? "active" : "";
  }

  if (key === "courses") {
    return pathname === "/courses" || /^\/courses\/\d+\/knowledge-base\/?$/.test(pathname) ? "active" : "";
  }

  return pathname === "/profile/interview" || /^\/courses\/\d+\/profile\/interview\/?$/.test(pathname) ? "active" : "";
}
