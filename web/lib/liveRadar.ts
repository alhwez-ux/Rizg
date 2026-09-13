import { toFiniteNumber } from "@/lib/screener";

export type LiveRadarSignal = "entry" | "exit" | "trap" | "neutral";

export interface LiveRadarTrap {
  kind: string;
  label: string;
}

export interface LiveRadarReport {
  symbol: string;
  signal: LiveRadarSignal;
  entry: boolean;
  exit: boolean;
  trap: LiveRadarTrap | null;
  flow_verified: boolean;
  score: number;
  net_flow: number;
  inflow: number;
  outflow: number;
  buy_volume: number;
  sell_volume: number;
  buy_ratio: number | null;
  sell_ratio: number | null;
  last_price: number | null;
  vwap: number | null;
  atr: number | null;
  suggested_entry: number | null;
  suggested_exit: number | null;
  target_price: number | null;
  stop_loss: number | null;
  change_percent: number | null;
  trade_count: number;
  reasons: string[];
}

export interface LiveRadarResponse {
  symbol: string;
  success: boolean;
  source: string;
  analysis: LiveRadarReport;
}

export async function fetchLiveRadar(
  symbol: string,
  interval = "1d",
): Promise<LiveRadarResponse> {
  const ticker = symbol.trim();
  const response = await fetch(`/api/v1/radar/live/${ticker}?interval=${interval}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    throw new Error(extractError(payload, response.status));
  }
  return parseLiveRadarPayload(payload, ticker);
}

export function parseLiveRadarPayload(
  payload: Record<string, unknown> | null,
  fallbackSymbol: string,
): LiveRadarResponse {
  const analysis = parseReport(payload?.analysis);
  if (!analysis) {
    throw new Error("تعذر قراءة تقرير الرادار");
  }
  return {
    symbol: String(payload?.symbol ?? fallbackSymbol),
    success: Boolean(payload?.success ?? true),
    source: String(payload?.source ?? "Sahm API"),
    analysis,
  };
}

function extractError(payload: Record<string, unknown> | null, status: number): string {
  if (!payload) return `HTTP ${status}`;
  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (typeof payload.message === "string" && payload.message.trim()) return payload.message;
  if (typeof payload.error === "string" && payload.error.trim()) return payload.error;
  return `HTTP ${status}`;
}

function parseReport(raw: unknown): LiveRadarReport | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const trapRaw = row.trap && typeof row.trap === "object" ? (row.trap as Record<string, unknown>) : null;
  const signal = String(row.signal ?? "neutral");
  return {
    symbol: String(row.symbol ?? ""),
    signal: signal === "entry" || signal === "exit" || signal === "trap" ? signal : "neutral",
    entry: Boolean(row.entry),
    exit: Boolean(row.exit),
    trap: trapRaw
      ? { kind: String(trapRaw.kind ?? ""), label: String(trapRaw.label ?? "") }
      : null,
    flow_verified: Boolean(row.flow_verified),
    score: toFiniteNumber(row.score) ?? 0,
    net_flow: toFiniteNumber(row.net_flow) ?? 0,
    inflow: toFiniteNumber(row.inflow) ?? 0,
    outflow: toFiniteNumber(row.outflow) ?? 0,
    buy_volume: toFiniteNumber(row.buy_volume) ?? 0,
    sell_volume: toFiniteNumber(row.sell_volume) ?? 0,
    buy_ratio: toFiniteNumber(row.buy_ratio),
    sell_ratio: toFiniteNumber(row.sell_ratio),
    last_price: toFiniteNumber(row.last_price),
    vwap: toFiniteNumber(row.vwap),
    atr: toFiniteNumber(row.atr),
    suggested_entry: toFiniteNumber(row.suggested_entry),
    suggested_exit: toFiniteNumber(row.suggested_exit),
    target_price: toFiniteNumber(row.target_price),
    stop_loss: toFiniteNumber(row.stop_loss),
    change_percent: toFiniteNumber(row.change_percent),
    trade_count: toFiniteNumber(row.trade_count) ?? 0,
    reasons: Array.isArray(row.reasons) ? row.reasons.map(String) : [],
  };
}
