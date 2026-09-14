import { apiFetch, apiUrl } from "@/lib/api";

export const SESSION_REFRESHED_EVENT = "rizg-session-refreshed";

export interface TickChartStatus {
  enabled: boolean;
  connected: boolean;
  trades_live: boolean;
  depth_live: boolean;
  mode?: string;
  autosync_enabled: boolean;
  autosync_watching: boolean;
  autosync_files: number;
  autosync_dirs?: string[];
  last_file: string | null;
  last_ingested: number;
  last_sync_at: string | null;
  source: string;
  quote_mode?: "live" | "last_close" | "waiting" | string;
  last_quotes?: number;
}

export interface SessionRefreshResult {
  success: boolean;
  count: number;
  quote_mode?: string;
  live?: number;
  last_close?: number;
}

let refreshInflight: Promise<SessionRefreshResult> | null = null;

function notifySessionRefreshed() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(SESSION_REFRESHED_EVENT));
}

export async function fetchTickChartStatus(): Promise<TickChartStatus | null> {
  try {
    const response = await apiFetch("/api/v1/tickchart/status");
    const payload = (await response.json().catch(() => null)) as TickChartStatus | null;
    if (!response.ok || !payload) return null;
    return payload;
  } catch {
    return null;
  }
}

export async function refreshTickChartLive(): Promise<SessionRefreshResult> {
  if (refreshInflight) return refreshInflight;
  refreshInflight = pullSessionTape().finally(() => {
    refreshInflight = null;
  });
  return refreshInflight;
}

async function pullSessionTape(): Promise<SessionRefreshResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45_000);
  try {
    const response = await apiFetch("/api/v1/tickchart/refresh", {
      method: "POST",
      body: "{}",
      signal: controller.signal,
    });
    const payload = (await response.json().catch(() => null)) as SessionRefreshResult | null;
    if (!response.ok) {
      throw new Error("تعذر تحديث رادار تكرتشارت");
    }
    notifySessionRefreshed();
    return {
      success: Boolean(payload?.success ?? true),
      count: Number(payload?.count || 0),
      quote_mode: payload?.quote_mode,
      live: payload?.live,
      last_close: payload?.last_close,
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function followTickChartSymbol(symbol: string): Promise<{ symbol: string; name: string }> {
  const response = await apiFetch("/api/v1/tickchart/follow", {
    method: "POST",
    body: JSON.stringify({ symbol }),
  });
  const payload = (await response.json().catch(() => null)) as {
    symbol?: string;
    name?: string;
    detail?: string;
    message?: string;
  } | null;
  if (!response.ok || !payload?.symbol) {
    throw new Error(payload?.message || payload?.detail || "تعذر متابعة الرمز");
  }
  return { symbol: payload.symbol, name: payload.name || payload.symbol };
}

export async function uploadTickChartFile(file: File): Promise<number> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(apiUrl("/api/v1/tickchart/upload"), {
    method: "POST",
    body,
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => null)) as { ingested?: number; message?: string; detail?: string } | null;
  if (!response.ok) {
    throw new Error(payload?.message || payload?.detail || "تعذر رفع ملف تكرتشارت");
  }
  return Number(payload?.ingested || 0);
}
