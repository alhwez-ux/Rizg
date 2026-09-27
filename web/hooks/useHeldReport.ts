"use client";

import { useEffect, useRef, useState } from "react";

import { RADAR_DISPLAY_MS } from "@/lib/radarHold";
import type { LiveRadarReport } from "@/lib/liveRadar";

export function useHeldReport(symbol: string, report: LiveRadarReport | null): LiveRadarReport | null {
  const pending = useRef(report);
  pending.current = report;
  const [slot, setSlot] = useState<{ symbol: string; report: LiveRadarReport; shownAt: number } | null>(null);

  useEffect(() => {
    if (!report) return;
    const now = Date.now();
    setSlot((current) => {
      if (!current || current.symbol !== symbol) return { symbol, report, shownAt: now };
      if (now - current.shownAt >= RADAR_DISPLAY_MS) return { symbol, report, shownAt: now };
      return current;
    });
  }, [report, symbol]);

  useEffect(() => {
    if (!slot || slot.symbol !== symbol) return;
    const wait = RADAR_DISPLAY_MS - (Date.now() - slot.shownAt);
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
