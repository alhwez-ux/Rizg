"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { wsUrlTape } from "@/lib/api";
import { parseRecommendation, type RecommendationFlag } from "@/lib/liquidity";
import { recommendationFromScreener, type ScreenerRow } from "@/lib/screener";

const MAX_BACKOFF_MS = 10_000;

export function useRadarRecommendations(
  screenerRows: ScreenerRow[],
): Map<string, RecommendationFlag | null> {
  const seeded = useMemo(() => {
    const map = new Map<string, RecommendationFlag | null>();
    for (const row of screenerRows) {
      map.set(row.symbol, recommendationFromScreener(row));
    }
    return map;
  }, [screenerRows]);

  const [live, setLive] = useState<Map<string, RecommendationFlag | null>>(new Map());
  const pending = useRef(new Map<string, RecommendationFlag | null>());
  const rafId = useRef<number | null>(null);

  useEffect(() => {
    let stopped = false;
    let retry = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | null = null;
    const url = wsUrlTape();

    const flush = () => {
      rafId.current = null;
      if (pending.current.size === 0) return;
      const batch = new Map(pending.current);
      pending.current.clear();
      setLive((prev) => {
        const next = new Map(prev);
        for (const [symbol, flag] of batch) {
          next.set(symbol, flag);
        }
        return next;
      });
    };

    const scheduleFlush = () => {
      if (rafId.current != null) return;
      rafId.current = requestAnimationFrame(flush);
    };

    const connect = () => {
      if (stopped) return;
      const ws = new WebSocket(url);
      socket = ws;

      ws.onopen = () => {
        if (stopped) {
          ws.close();
          return;
        }
        retry = 0;
      };

      ws.onmessage = (event) => {
        if (stopped) return;
        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(String(event.data)) as Record<string, unknown>;
        } catch {
          return;
        }
        const kind = payload.type;
        if (kind === "ping" || kind === "pong" || kind === "error" || kind === "alert") {
          return;
        }
        if (!("recommendation" in payload)) return;
        const symbol = String(payload.symbol ?? "").trim();
        if (!symbol) return;
        pending.current.set(symbol, parseRecommendation(payload.recommendation));
        scheduleFlush();
      };

      ws.onclose = () => {
        if (stopped || socket !== ws) return;
        const delay = Math.min(MAX_BACKOFF_MS, 400 * 2 ** retry);
        retry += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (rafId.current != null) cancelAnimationFrame(rafId.current);
      pending.current.clear();
      socket?.close();
    };
  }, []);

  return useMemo(() => {
    const merged = new Map(seeded);
    for (const [symbol, flag] of live) {
      merged.set(symbol, flag);
    }
    return merged;
  }, [live, seeded]);
}
