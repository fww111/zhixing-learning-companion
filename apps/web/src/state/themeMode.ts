import { useEffect, useState } from "react";

const THEME_KEY = "pla_theme_mode";

export type ThemeMode = "light" | "dark";

export function loadThemeMode(storage: Pick<Storage, "getItem"> = localStorage): ThemeMode {
  const value = storage.getItem(THEME_KEY);
  return value === "dark" ? "dark" : "light";
}

export function saveThemeMode(mode: ThemeMode, storage: Pick<Storage, "setItem"> = localStorage): void {
  storage.setItem(THEME_KEY, mode);
}

export function applyThemeMode(mode: ThemeMode, doc: Pick<Document, "documentElement"> = document): void {
  if (mode === "dark") {
    doc.documentElement.dataset.theme = "dark";
  } else {
    delete doc.documentElement.dataset.theme;
  }
}

/** 主题模式 hook：切换 data-theme 并持久化。 */
export function useThemeMode(): [ThemeMode, (mode: ThemeMode) => void] {
  const [mode, setMode] = useState<ThemeMode>(() => loadThemeMode());

  useEffect(() => {
    applyThemeMode(mode);
  }, [mode]);

  function update(next: ThemeMode) {
    setMode(next);
    saveThemeMode(next);
    applyThemeMode(next);
  }

  return [mode, update];
}
