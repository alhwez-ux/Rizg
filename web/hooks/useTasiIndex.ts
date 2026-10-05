"use client";

import { useEffect, useState } from "react";

import { wsUrlTape } from "@/lib/api";
import { useConnectionGuard } from "@/hooks/useConnectionGuard";
import type { ConnectionStatus } from "@/lib/liquidity";

export interface TasiIndexQuote {
  value: number | null;
  change: number | null;
  changePercent: number | null;
}

const EMPTY: TasiIndexQuote = { value: null, change: null, changePercent: null };

export function useTasiIndex(): { quote: TasiIndexQuote; status: ConnectionStatus } {
  const [quote, setQuote] = useState<TasiIndexQuote>(EMPTY);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const { isConnected } = useConnectionGuard();

  useEffect(() => {
    if (!isConnected) {
      setStatus("offline");
      return;
    }
    let alive = true;
    const load = async () => {
      try {
        const response = await fetch("/api/market/tasi", { cache: "no-store" });
        const payload = (await response.json()) as Record<string, unknown>;
        if (!alive) return;
        setQuote((current) => mergeQuote(current, payload));
      } catch {
        /* the socket remains the live source */
      }
    };
    void load();
    return () => {
      alive = false;
    };
  }, [isConnected]);

  useEffect(() => {
    if (!isConnected) return;
    let stopped = false;
    let retry = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | null = null;

    const connect = () => {
      if (stopped) return;
      setStatus(retry === 0 ? "connecting" : "reconnecting");
      const ws = new WebSocket(`${wsUrlTape()}?symbols=TASI`);
      socket = ws;
      ws.onopen = () => {
        if (stopped) return;
        retry = 0;
        setStatus("live");
      };
      ws.onmessage = (event) => {
        if (stopped) return;
        try {
          const payload = JSON.parse(event.data) as Record<string, unknown>;
          if (payload.type === "ping") {
            if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action: "ping" }));
            return;
          }
          const next = parseIndexMessage(payload);
          if (!next) return;
          setQuote((current) => mergeQuote(current, next));
        } catch {
          /* ignore non-json frames */
        }
      };
      ws.onerror = () => {
        ws.close();
      };
      ws.onclose = () => {
        if (stopped) return;
        retry += 1;
        if (retry >= 5) {
          setStatus("offline");
          return;
        }
        setStatus("reconnecting");
        reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** (retry - 1), 10_000));
      };
    };

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
      setStatus("offline");
    };
  }, [isConnected]);

  return { quote, status };
}

function parseIndexMessage(payload: Record<string, unknown>): Record<string, unknown> | null {
  const symbol = String(payload.symbol ?? "").trim().toUpperCase();
  if (payload.type !== "index" && symbol !== "TASI") return null;
  if (payload.value == null && payload.change == null && payload.change_percent == null) return null;
  return payload;
}

function mergeQuote(current: TasiIndexQuote, payload: Record<string, unknown>): TasiIndexQuote {
  const value = finite(payload.value);
  const change = finite(payload.change);
  const changePercent = finite(payload.changePercent ?? payload.change_percent);
  const next = {
    value: value ?? current.value,
    change: change ?? current.change,
    changePercent: changePercent ?? current.changePercent,
  };
  if (next.value === current.value && next.change === current.change && next.changePercent === current.changePercent) {
    return current;
  }
  return next;
}

function finite(value: unknown): number | null {
  if (value == null || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
