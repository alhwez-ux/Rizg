"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiUrl } from "@/lib/api";
import { parseRow, toFiniteNumber, type ScreenerSnapshot } from "@/lib/screener";

const POLL_MS = 2_000;

interface UseScreenerState {
  snapshot: ScreenerSnapshot | null;
  error: string | null;
  adding: boolean;
  addSymbol: (symbol: string) => Promise<void>;
  removeSymbol: (symbol: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useScreener(): UseScreenerState {
  const [snapshot, setSnapshot] = useState<ScreenerSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch(apiUrl("/api/v1/screener"), { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = (await response.json()) as Record<string, unknown>;
      if (!alive.current) return;
      setSnapshot({
        watchlist: Array.isArray(payload.watchlist)
          ? payload.watchlist.map((row) => parseRow(row as Record<string, unknown>))
          : [],
        radar: Array.isArray(payload.radar)
          ? payload.radar.map((row) => parseRow(row as Record<string, unknown>))
          : [],
        pulse: {
          index: String((payload.pulse as { index?: string } | undefined)?.index ?? "TASI"),
          index_value: toFiniteNumber((payload.pulse as { index_value?: unknown } | undefined)?.index_value),
          index_change_percent: toFiniteNumber(
            (payload.pulse as { index_change_percent?: unknown } | undefined)?.index_change_percent,
          ),
          advancing: (payload.pulse as { advancing?: number } | undefined)?.advancing ?? null,
          declining: (payload.pulse as { declining?: number } | undefined)?.declining ?? null,
          delayed: Boolean((payload.pulse as { delayed?: boolean } | undefined)?.delayed ?? payload.delayed),
        },
        scanned: Number(payload.scanned) || 0,
        delayed: Boolean(payload.delayed),
        updated_at: payload.updated_at == null ? null : String(payload.updated_at),
      });
      setError(null);
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error ? err.message : "تعذر تحميل الرادار");
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, POLL_MS);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  const addSymbol = useCallback(
    async (symbol: string) => {
      setAdding(true);
      try {
        const response = await fetch(apiUrl("/api/v1/watchlist"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol }),
        });
        if (!response.ok) {
          const body = (await response.json().catch(() => null)) as { message?: string } | null;
          throw new Error(body?.message ?? "تعذر إضافة الرمز");
        }
        await refresh();
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "تعذر إضافة الرمز");
        throw err;
      } finally {
        setAdding(false);
      }
    },
    [refresh],
  );

  const removeSymbol = useCallback(
    async (symbol: string) => {
      const response = await fetch(apiUrl(`/api/v1/watchlist/${symbol}`), { method: "DELETE" });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { message?: string } | null;
        throw new Error(body?.message ?? "تعذر حذف الرمز");
      }
      await refresh();
    },
    [refresh],
  );

  return { snapshot, error, adding, addSymbol, removeSymbol, refresh };
}
