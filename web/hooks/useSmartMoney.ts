"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSmartMoneyScan, type SmartMoneyScanResponse } from "@/lib/smartMoney";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";

const POLL_MS = 12_000;

export function useSmartMoney() {
  const [payload, setPayload] = useState<SmartMoneyScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchSmartMoneyScan();
      if (!alive.current) return;
      setPayload(next);
      setError(null);
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error ? err.message : "تعذر جلب رادار الصناديق");
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

  return {
    payload,
    rows: payload?.data ?? [],
    hint: payload?.hint ?? "",
    loading,
    error,
    refresh,
  };
}
