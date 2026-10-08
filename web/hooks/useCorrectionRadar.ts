"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useConnectionGuard } from "@/hooks/useConnectionGuard";
import { fetchCorrectionRadar, type CorrectionRadarResponse } from "@/lib/correctionRadar";
import { sessionPollMs } from "@/lib/sessionPoll";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";

const POLL_MS = 20_000;

export function useCorrectionRadar() {
  const [payload, setPayload] = useState<CorrectionRadarResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [late, setLate] = useState(false);
  const alive = useRef(true);
  const hasData = useRef(false);
  const slowTimer = useRef(0);
  const { isConnected } = useConnectionGuard();

  const refresh = useCallback(async () => {
    window.clearTimeout(slowTimer.current);
    if (hasData.current) {
      slowTimer.current = window.setTimeout(() => {
        if (alive.current) setLate(true);
      }, 1_200);
    }
    try {
      const next = await fetchCorrectionRadar();
      if (!alive.current) return;
      hasData.current = true;
      setPayload(next);
      setError(null);
      setLate(false);
    } catch (err) {
      if (!alive.current) return;
      if (!hasData.current) {
        setError(err instanceof Error ? err.message : "تعذر جلب منبه التصحيح");
      } else {
        setLate(true);
      }
    } finally {
      window.clearTimeout(slowTimer.current);
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
      window.clearTimeout(slowTimer.current);
      window.removeEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    };
  }, [isConnected, refresh]);

  return { payload, rows: payload?.data ?? [], loading, error, late, refresh };
}
