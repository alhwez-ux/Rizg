"use client";

import { useEffect, useState } from "react";

import { isTasiLiveSession, tasiPhaseLabel, tasiSessionPhase, type TasiPhase } from "@/lib/tasiClock";
import { useConnectionGuard } from "@/hooks/useConnectionGuard";
import { fetchSchedulerStatus, type SchedulerStatus } from "@/lib/tasiScheduler";

const POLL_MS = 15_000;

export function useTasiSession() {
  const [clock, setClock] = useState(() => new Date());
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const { isConnected } = useConnectionGuard();

  useEffect(() => {
    const tick = window.setInterval(() => setClock(new Date()), 15_000);
    return () => window.clearInterval(tick);
  }, []);

  useEffect(() => {
    if (!isConnected) return;
    let alive = true;
    const load = async () => {
      const next = await fetchSchedulerStatus();
      if (alive) setStatus(next);
    };
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [isConnected]);

  const localPhase = tasiSessionPhase(clock);
  const phase = (status?.phase as TasiPhase | undefined) || localPhase;
  const live = Boolean(status?.intraday) || phase === "open" || isTasiLiveSession(clock);
  const buttonLabel = live ? "توصيات لحظية" : "توصيات الإغلاق";
  return {
    status,
    phase,
    live,
    buttonLabel,
    label: status?.phase_label || tasiPhaseLabel(localPhase),
  };
}
