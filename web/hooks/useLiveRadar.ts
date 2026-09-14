"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchLiveRadar, type LiveRadarResponse } from "@/lib/liveRadar";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";

const POLL_MS = 2_000;

export function useLiveRadar(symbol: string, interval = "1d") {
  const [data, setData] = useState<LiveRadarResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const alive = useRef(true);
  const hasData = useRef(false);

  const refresh = useCallback(async () => {
    const ticker = symbol.trim();
    if (!ticker) return;
    if (!hasData.current) setLoading(true);
    try {
      const payload = await fetchLiveRadar(ticker, interval);
      if (!alive.current) return;
      if (payload) {
        hasData.current = true;
        setData(payload);
        setError(null);
      }
    } catch (err) {
      if (!alive.current) return;
      if (!hasData.current) {
        setData(null);
        setError(err instanceof Error ? err.message : "تعذر جلب رادار السيولة من تكرتشارت");
      }
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [interval, symbol]);

  useEffect(() => {
    alive.current = true;
    hasData.current = false;
    setData(null);
    setError(null);
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

  return { data, error, loading, refresh };
}
