"use client";

import { useCallback, useEffect, useState } from "react";

import {
  VISIBILITY_DEFAULTS,
  VISIBILITY_STORAGE_KEY,
  readVisibility,
  type VisibilityKey,
  type VisibilityMap,
} from "@/lib/dashboardVisibility";

export function useDashboardVisibility() {
  const [map, setMap] = useState<VisibilityMap>(VISIBILITY_DEFAULTS);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      setMap(readVisibility(window.localStorage.getItem(VISIBILITY_STORAGE_KEY)));
    } catch {
      setMap(VISIBILITY_DEFAULTS);
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(VISIBILITY_STORAGE_KEY, JSON.stringify(map));
    } catch {
      /* private mode */
    }
  }, [map, ready]);

  const toggle = useCallback((key: VisibilityKey) => {
    setMap((current) => ({ ...current, [key]: !current[key] }));
  }, []);

  const reset = useCallback(() => {
    setMap(VISIBILITY_DEFAULTS);
  }, []);

  return { map, toggle, reset };
}
