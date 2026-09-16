"use client";

import { useCallback, useLayoutEffect, useState } from "react";

import {
  THEME_DARK,
  THEME_LIGHT,
  THEME_STORAGE_KEY,
  applyTheme,
  isDisplayTheme,
  readStoredTheme,
  type DisplayTheme,
} from "@/lib/theme";

function themeFromDocument(): DisplayTheme {
  if (typeof document === "undefined") return THEME_DARK;
  const value = document.documentElement.getAttribute("data-theme");
  return isDisplayTheme(value) ? value : readStoredTheme();
}

export function useTheme() {
  const [theme, setThemeState] = useState<DisplayTheme>(THEME_DARK);

  useLayoutEffect(() => {
    const stored = readStoredTheme();
    setThemeState(stored);
    applyTheme(stored);

    const onStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY || !isDisplayTheme(event.newValue)) return;
      applyTheme(event.newValue);
      setThemeState(event.newValue);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setTheme = useCallback((next: DisplayTheme) => {
    applyTheme(next);
    setThemeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    const next = themeFromDocument() === THEME_LIGHT ? THEME_DARK : THEME_LIGHT;
    applyTheme(next);
    setThemeState(next);
  }, []);

  return { theme, setTheme, toggleTheme, isDay: theme === THEME_LIGHT };
}
