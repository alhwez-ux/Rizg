"use client";

import { useEffect, useRef, useState } from "react";

import { RADAR_DISPLAY_MS } from "@/lib/radarHold";
import type { LiveRadarReport } from "@/lib/liveRadar";
import { OPEN_POLL_MS } from "@/lib/sessionPoll";
import { tasiSessionPhase } from "@/lib/tasiClock";

function holdMs(): number {
  const phase = tasiSessionPhase();
  if (phase === "preopen" || phase === "open" || phase === "auction") return OPEN_POLL_MS;
  return RADAR_DISPLAY_MS;
}

export function useHeldReport(symbol: string, report: LiveRadarReport | null): LiveRadarReport | null {
  const pending = useRef(report);
  pending.current = report;
  const [slot, setSlot] = useState<{ symbol: string; report: LiveRadarReport; shownAt: number } | null>(null);

  useEffect(() => {
    if (!report) return;
    const now = Date.now();
    setSlot((current) => {
      if (!current || current.symbol !== symbol) return { symbol, report, shownAt: now };
      if (now - current.shownAt >= holdMs()) return { symbol, report, shownAt: now };
      return current;
    });
  }, [report, symbol]);

  useEffect(() => {
    if (!slot || slot.symbol !== symbol) return;
    const wait = holdMs() - (Date.now() - slot.shownAt);
    if (wait <= 0) return;
    const timer = window.setTimeout(() => {
      const next = pending.current;
      if (!next) return;
      setSlot({ symbol, report: next, shownAt: Date.now() });
    }, wait);
    return () => window.clearTimeout(timer);
  }, [slot, symbol]);

  if (slot?.symbol === symbol) return slot.report;
  return report;
}
