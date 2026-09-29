"use client";

import { createContext, createElement, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";

import {
  beatConnection,
  connectionClientId,
  fetchConnectionStatus,
  releaseConnection,
  type ConnectionSnapshot,
} from "@/lib/connectionGuard";

const POLL_MS = 15_000;

export interface ConnectionGuardValue {
  isConnected: boolean;
  healthy: boolean;
  planActive: boolean;
  planReason: string | null;
  checking: boolean;
}

const IDLE: ConnectionGuardValue = {
  isConnected: false,
  healthy: false,
  planActive: false,
  planReason: null,
  checking: true,
};

const ConnectionGuardContext = createContext<ConnectionGuardValue>(IDLE);

function allowsSession(pathname: string | null): boolean {
  return Boolean(pathname) && pathname !== "/login";
}

export function ConnectionGuardProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [snapshot, setSnapshot] = useState<ConnectionSnapshot | null>(null);
  const [checking, setChecking] = useState(true);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const sync = () => setVisible(document.visibilityState === "visible");
    sync();
    document.addEventListener("visibilitychange", sync);
    return () => document.removeEventListener("visibilitychange", sync);
  }, []);

  useEffect(() => {
    if (!allowsSession(pathname) || !visible) {
      setChecking(false);
      setSnapshot((current) =>
        current
          ? { ...current, is_connected: false, clients: 0 }
          : {
              healthy: true,
              plan_active: true,
              plan_reason: null,
              clients: 0,
              is_connected: false,
            },
      );
      if (!visible) releaseConnection(connectionClientId());
      return;
    }

    let alive = true;
    const clientId = connectionClientId();

    const tick = async () => {
      const status = await fetchConnectionStatus();
      if (!alive) return;
      if (!status.healthy || !status.plan_active) {
        setSnapshot({ ...status, is_connected: false });
        setChecking(false);
        return;
      }
      if (status.unsupported) {
        setSnapshot({ ...status, is_connected: true });
        setChecking(false);
        return;
      }
      const beat = await beatConnection(clientId);
      if (!alive) return;
      const next = beat ?? status;
      setSnapshot({
        ...next,
        is_connected: next.healthy && next.plan_active && next.is_connected,
      });
      setChecking(false);
    };

    void tick();
    const timer = window.setInterval(() => {
      void tick();
    }, POLL_MS);
    const release = () => releaseConnection(clientId);
    window.addEventListener("pagehide", release);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("pagehide", release);
      release();
    };
  }, [pathname, visible]);

  const value = useMemo<ConnectionGuardValue>(() => {
    if (!allowsSession(pathname) || !visible) {
      return {
        isConnected: false,
        healthy: snapshot?.healthy ?? true,
        planActive: snapshot?.plan_active ?? true,
        planReason: snapshot?.plan_reason ?? null,
        checking: false,
      };
    }
    return {
      // Readings stay available when the live plan or socket heartbeat is down.
      // The heartbeat still arms Sahm/TickChart ingestion; it must not blank the tape.
      isConnected: true,
      healthy: snapshot?.healthy !== false,
      planActive: snapshot?.plan_active !== false,
      planReason: snapshot?.plan_reason ?? null,
      checking,
    };
  }, [checking, pathname, snapshot, visible]);

  return createElement(ConnectionGuardContext.Provider, { value }, children);
}

export function useConnectionGuard(): ConnectionGuardValue {
  return useContext(ConnectionGuardContext);
}
