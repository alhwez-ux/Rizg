import { apiFetch, apiUrl } from "@/lib/api";

export interface TickChartStatus {
  enabled: boolean;
  connected: boolean;
  trades_live: boolean;
  depth_live: boolean;
  mode?: string;
  autosync_enabled: boolean;
  autosync_watching: boolean;
  autosync_files: number;
  last_file: string | null;
  last_ingested: number;
  last_sync_at: string | null;
  source: string;
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

export async function refreshTickChartLive(): Promise<void> {
  const response = await apiFetch("/api/v1/tickchart/refresh", { method: "POST", body: "{}" });
  if (!response.ok) {
    throw new Error("تعذر تحديث رادار تكرتشارت");
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
