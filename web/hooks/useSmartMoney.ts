"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useConnectionGuard } from "@/hooks/useConnectionGuard";
import { fetchSmartMoneyScan, type SmartMoneyScanResponse } from "@/lib/smartMoney";
import { sessionPollMs } from "@/lib/sessionPoll";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";

const POLL_MS = 12_000;

export function useSmartMoney() {
  const [payload, setPayload] = useState<SmartMoneyScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  const { isConnected } = useConnectionGuard();

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
    if (!isConnected) {
      setLoading(false);
      return;
    }
    alive.current = true;
    void refresh();
    let timer = 0;
    const arm = () => {
      timer = window.setTimeout(() => {
        void refresh();
        arm();
      }, sessionPollMs(POLL_MS));
    };
    arm();
    const onRefresh = () => {
      void refresh();
    };
    window.addEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    return () => {
      alive.current = false;
      window.clearTimeout(timer);
      window.removeEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    };
  }, [isConnected, refresh]);

  return {
    payload,
    rows: payload?.data ?? [],
    hint: payload?.hint ?? "",
    loading,
    error,
    refresh,
  };
}
