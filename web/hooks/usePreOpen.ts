"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchPreOpenScan, type PreOpenScanResponse } from "@/lib/preopen";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";

const LIVE_POLL_MS = 8_000;
const IDLE_POLL_MS = 30_000;

export function usePreOpen() {
  const [payload, setPayload] = useState<PreOpenScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  const inWindow = Boolean(payload?.in_window);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchPreOpenScan();
      if (!alive.current) return;
      setPayload(next);
      setError(null);
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error ? err.message : "تعذر جلب قراءة ماقبل الافتتاح");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, inWindow ? LIVE_POLL_MS : IDLE_POLL_MS);
    const onRefresh = () => {
      void refresh();
    };
    window.addEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
      window.removeEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    };
  }, [inWindow, refresh]);

  return {
    payload,
    rows: payload?.data ?? [],
    hint: payload?.hint ?? "",
    inWindow,
    loading,
    error,
    refresh,
  };
}
