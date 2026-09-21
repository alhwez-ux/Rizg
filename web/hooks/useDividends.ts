"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchActiveDividends, type DividendRow } from "@/lib/dividends";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";

const POLL_MS = 60_000;

export function useDividends(pureOnly: boolean) {
  const [rows, setRows] = useState<DividendRow[]>([]);
  const [hint, setHint] = useState("");
  const [asOf, setAsOf] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const payload = await fetchActiveDividends(pureOnly);
      if (!alive.current) return;
      setRows(payload.data);
      setHint(payload.hint);
      setAsOf(payload.as_of);
      setError(null);
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error ? err.message : "تعذر جلب أخبار الأرباح والتوزيعات");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [pureOnly]);

  useEffect(() => {
    alive.current = true;
    setLoading(true);
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

  return { rows, hint, asOf, error, loading, refresh };
}
