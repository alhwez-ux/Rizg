"use client";

import { useEffect, useState } from "react";

import { tasiTapeChange } from "@/lib/marketData";
import { toneFromChange, type MarketTone } from "@/lib/market-tone";

const POLL_MS = 30_000;

export function useTasiTone(screenerChange?: number | null): {
  tone: MarketTone;
  changePercent: number | null;
} {
  const [fallback, setFallback] = useState<number | null>(null);

  useEffect(() => {
    if (screenerChange != null) return;
    let alive = true;

    const load = async () => {
      try {
        const response = await fetch("/api/market/tasi", { cache: "no-store" });
        const payload = (await response.json()) as { changePercent?: unknown };
        if (!alive) return;
        const parsed = typeof payload.changePercent === "number" ? payload.changePercent : Number(payload.changePercent);
        setFallback(Number.isFinite(parsed) ? parsed : null);
      } catch {
        if (alive) setFallback(null);
      }
    };

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [screenerChange]);

  const changePercent = screenerChange ?? fallback ?? tasiTapeChange();
  return { tone: toneFromChange(changePercent), changePercent };
}
