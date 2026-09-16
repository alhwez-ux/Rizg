"use client";

import { useCallback, useEffect, useState } from "react";

import {
  THEME_DARK,
  THEME_LIGHT,
  THEME_STORAGE_KEY,
  applyTheme,
  isDisplayTheme,
  readStoredTheme,
  type DisplayTheme,
} from "@/lib/theme";

export function useTheme() {
  const [theme, setThemeState] = useState<DisplayTheme>(THEME_DARK);

  useEffect(() => {
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
    setThemeState((current) => {
      const next = current === THEME_DARK ? THEME_LIGHT : THEME_DARK;
      applyTheme(next);
      return next;
    });
  }, []);

  return { theme, setTheme, toggleTheme, isDay: theme === THEME_LIGHT };
}
