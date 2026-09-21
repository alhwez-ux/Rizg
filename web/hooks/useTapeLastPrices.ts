"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { wsUrlTape } from "@/lib/api";
import { parseTick } from "@/lib/liquidity";

const MAX_BACKOFF_MS = 10_000;

export function useTapeLastPrices(symbols: string[]): Map<string, number> {
  const wantedKey = useMemo(
    () =>
      [
        ...new Set(
          symbols
            .map((symbol) => symbol.trim().toUpperCase())
            .filter(Boolean)
            .sort(),
        ),
      ].join(","),
    [symbols],
  );
  const wanted = useMemo(
    () => new Set(wantedKey ? wantedKey.split(",") : []),
    [wantedKey],
  );
  const [live, setLive] = useState<Map<string, number>>(new Map());
  const pending = useRef(new Map<string, number>());
  const rafId = useRef<number | null>(null);
  const wantedRef = useRef(wanted);
  wantedRef.current = wanted;

  useEffect(() => {
    if (wanted.size === 0) return;
    let stopped = false;
    let retry = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | null = null;

    const flush = () => {
      rafId.current = null;
      if (pending.current.size === 0) return;
      const batch = new Map(pending.current);
      pending.current.clear();
      setLive((prev) => {
        const next = new Map(prev);
        for (const [symbol, price] of batch) {
          next.set(symbol, price);
        }
        return next;
      });
    };

    const connect = () => {
      if (stopped) return;
      const ws = new WebSocket(wsUrlTape());
      socket = ws;
      ws.onopen = () => {
        if (stopped) {
          ws.close();
          return;
        }
        retry = 0;
        ws.send(JSON.stringify({ action: "subscribe", symbols: [...wantedRef.current] }));
      };
      ws.onmessage = (event) => {
        if (stopped) return;
        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(String(event.data)) as Record<string, unknown>;
        } catch {
          return;
        }
        const tick = parseTick(payload);
        const symbol = String(tick?.symbol || payload.symbol || "").toUpperCase();
        const price = tick?.lastPrice ?? tick?.price ?? Number(payload.last_price ?? payload.price);
        if (!symbol || !wantedRef.current.has(symbol) || !Number.isFinite(price) || price <= 0) {
          return;
        }
        pending.current.set(symbol, price);
        if (rafId.current == null) {
          rafId.current = requestAnimationFrame(flush);
        }
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
  }, [wanted]);

  return live;
}
