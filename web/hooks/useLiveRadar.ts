"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchLiveRadar, type LiveRadarResponse } from "@/lib/liveRadar";
import { useConnectionGuard } from "@/hooks/useConnectionGuard";
import { sessionPollMs } from "@/lib/sessionPoll";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";

const POLL_MS = 60_000;

export function useLiveRadar(symbol: string, interval = "1d") {
  const [data, setData] = useState<LiveRadarResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [delayed, setDelayed] = useState(false);
  const [settling, setSettling] = useState(false);
  const alive = useRef(true);
  const hasData = useRef(false);
  const inflight = useRef(false);
  const queued = useRef(false);
  const slowTimer = useRef(0);
  const { isConnected } = useConnectionGuard();

  const refresh = useCallback(async () => {
    const ticker = symbol.trim();
    if (!ticker) return;
    if (inflight.current) {
      queued.current = true;
      return;
    }
    inflight.current = true;
    try {
      do {
        queued.current = false;
        if (!hasData.current) setLoading(true);
        else setUpdating(true);
        window.clearTimeout(slowTimer.current);
        if (hasData.current) {
          slowTimer.current = window.setTimeout(() => {
            if (alive.current) setSettling(true);
          }, 1_200);
        }
        try {
          const payload = await fetchLiveRadar(ticker, interval);
          if (!alive.current) return;
          if (payload) {
            hasData.current = true;
            setData((current) => keepRadarFlow(current, payload));
            setError(null);
            setDelayed(false);
            setSettling(false);
          }
        } catch (err) {
          if (!alive.current) return;
          if (!hasData.current) {
            setData(null);
            setError(err instanceof Error ? err.message : "تعذر جلب رادار السيولة من تكرتشارت");
          } else {
            setDelayed(true);
            setSettling(true);
          }
        } finally {
          window.clearTimeout(slowTimer.current);
          if (alive.current) {
            setLoading(false);
            setUpdating(false);
          }
        }
      } while (queued.current && alive.current);
    } finally {
      inflight.current = false;
    }
  }, [interval, symbol]);

  useEffect(() => {
    if (!isConnected) {
      setLoading(false);
      return;
    }
    alive.current = true;
    hasData.current = false;
    setData(null);
    setError(null);
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

  return { data, error, loading, updating, delayed, settling, refresh };
}

function keepRadarFlow(current: LiveRadarResponse | null, next: LiveRadarResponse): LiveRadarResponse {
  const previous = current?.analysis;
  if (!previous?.net_flow || next.analysis.net_flow) return next;
  return {
    ...next,
    analysis: {
      ...next.analysis,
      net_flow: previous.net_flow,
      change_percent: next.analysis.change_percent ?? previous.change_percent,
    },
  };
}
