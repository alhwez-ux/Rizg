import { apiFetch, apiUrl, HEAVY_API_TIMEOUT_MS } from "@/lib/api";

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

export interface TickChartQuote {
  symbol: string;
  name: string;
  last_price: number | null;
  price_change_pct: number;
  net_flow: number;
}

function parseQuoteRows(payload: { data?: unknown } | null): TickChartQuote[] {
  if (!payload || !Array.isArray(payload.data)) return [];
  return payload.data
    .map((row) => {
      const item = row as Record<string, unknown>;
      const symbol = String(item.symbol || "").trim();
      const price = Number(item.last_price ?? item.price);
      return {
        symbol,
        name: String(item.name || symbol),
        last_price: Number.isFinite(price) && price > 0 ? price : null,
        price_change_pct: Number(item.price_change_pct ?? item.change_percent) || 0,
        net_flow: Number(item.net_flow) || 0,
      };
    })
    .filter((row) => row.symbol.length === 4 && row.last_price != null)
    .slice(0, 120);
}

export async function fetchTickChartMarket(): Promise<TickChartQuote[]> {
  try {
    const tape = await apiFetch("/api/v1/tickchart/tape", { timeoutMs: 20_000 });
    const tapePayload = (await tape.json().catch(() => null)) as { data?: unknown } | null;
    const fromTape = parseQuoteRows(tapePayload);
    if (tape.ok && fromTape.length) return fromTape;
    const response = await apiFetch("/api/v1/tickchart/market", { timeoutMs: 60_000 });
    const payload = (await response.json().catch(() => null)) as { data?: unknown } | null;
    if (!response.ok) return [];
    return parseQuoteRows(payload);
  } catch {
    return [];
  }
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
  const response = await apiFetch("/api/v1/tickchart/refresh", {
    method: "POST",
    body: "{}",
    timeoutMs: HEAVY_API_TIMEOUT_MS,
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
