"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchLiveRadar, type LiveRadarResponse } from "@/lib/liveRadar";

const POLL_MS = 45_000;

export function useLiveRadar(symbol: string, interval = "1d") {
  const [data, setData] = useState<LiveRadarResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    const ticker = symbol.trim();
    if (!ticker) return;
    setLoading(true);
    try {
      const payload = await fetchLiveRadar(ticker, interval);
      if (!alive.current) return;
      if (payload?.analysis.last_price) {
        setData(payload);
        setError(null);
      } else {
        setData(null);
        setError("تعذر جلب رادار السيولة");
      }
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error ? err.message : "تعذر جلب رادار السيولة");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [interval, symbol]);

  useEffect(() => {
    alive.current = true;
    setData(null);
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, POLL_MS);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  return { data, error, loading, refresh };
}
