"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchUnderWatch, type UnderWatchRow } from "@/lib/underWatch";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";

const POLL_MS = 2_000;

export function useUnderWatch() {
  const [rows, setRows] = useState<UnderWatchRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const payload = await fetchUnderWatch();
      if (!alive.current) return;
      setRows(payload.data);
      setError(null);
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error ? err.message : "تعذر جلب الشركات تحت المراقبة");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, POLL_MS);
    const onRefresh = () => {
      void refresh();
    };
    window.addEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
      window.removeEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    };
  }, [refresh]);

  return { rows, error, loading, refresh };
}
