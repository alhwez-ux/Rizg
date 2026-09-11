"use client";

import { useEffect, useRef, useState } from "react";

import {
  DEFAULT_WS_URL,
  parseAlert,
  parseTick,
  pushSparkline,
  type AlertStreamPayload,
  type ConnectionStatus,
  type LiquidityAlertEvent,
  type LiquidityStreamPayload,
  type LiquidityTick,
} from "@/lib/liquidity";

export interface LiquiditySocketState {
  tick: LiquidityTick | null;
  sparkline: number[];
  alerts: LiquidityAlertEvent[];
  status: ConnectionStatus;
  attempts: number;
}

const MAX_BACKOFF_MS = 10_000;
const MAX_ALERTS = 40;

export function useLiquiditySocket(url: string = DEFAULT_WS_URL): LiquiditySocketState {
  const [tick, setTick] = useState<LiquidityTick | null>(null);
  const [sparkline, setSparkline] = useState<number[]>([]);
  const [alerts, setAlerts] = useState<LiquidityAlertEvent[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [attempts, setAttempts] = useState(0);

  const latestTick = useRef<LiquidityTick | null>(null);
  const latestSpark = useRef<number[]>([]);
  const dirty = useRef(false);
  const rafId = useRef<number | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let stopped = false;
    let retry = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    latestTick.current = null;
    latestSpark.current = [];
    setTick(null);
    setSparkline([]);
    setAlerts([]);

    const flush = () => {
      rafId.current = null;
      if (!dirty.current) return;
      dirty.current = false;
      setTick(latestTick.current);
      setSparkline(latestSpark.current);
    };

    const scheduleFlush = () => {
      if (rafId.current != null) return;
      rafId.current = requestAnimationFrame(flush);
    };

    const ingest = (payload: LiquidityStreamPayload) => {
      const next = parseTick(payload);
      if (!next) return;
      latestTick.current = next;
      latestSpark.current = pushSparkline(latestSpark.current, next.netFlow);
      dirty.current = true;
      scheduleFlush();
    };

    const connect = () => {
      if (stopped) return;
      setStatus(retry === 0 ? "connecting" : "reconnecting");
      setAttempts(retry);

      const ws = new WebSocket(url);
      socketRef.current = ws;

      ws.onopen = () => {
        if (stopped) return;
        retry = 0;
        setAttempts(0);
        setStatus("live");
      };

      ws.onmessage = (event) => {
        if (stopped) return;
        try {
          const payload = JSON.parse(event.data) as LiquidityStreamPayload | AlertStreamPayload;
          if (payload.type === "ping") {
            if (ws.readyState === WebSocket.OPEN) ws.send("ping");
            return;
          }
          if (payload.type === "alert") {
            const alert = parseAlert(payload as AlertStreamPayload);
            if (!alert) return;
            setAlerts((current) => [alert, ...current.filter((item) => item.id !== alert.id)].slice(0, MAX_ALERTS));
            if (typeof Notification !== "undefined" && Notification.permission === "granted") {
              new Notification(alert.title, { body: alert.message, tag: alert.id });
            }
            return;
          }
          ingest(payload);
        } catch {
          // Ignore keep-alive text frames that are not JSON.
        }
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onclose = () => {
        if (stopped) return;
        setStatus("reconnecting");
        const delay = Math.min(1000 * 2 ** retry, MAX_BACKOFF_MS);
        retry += 1;
        setAttempts(retry);
        reconnectTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (rafId.current != null) cancelAnimationFrame(rafId.current);
      socketRef.current?.close();
      socketRef.current = null;
      setStatus("offline");
    };
  }, [url]);

  return { tick, sparkline, alerts, status, attempts };
}
