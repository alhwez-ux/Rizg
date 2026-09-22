import { apiFetch } from "@/lib/api";
import { toFiniteNumber } from "@/lib/screener";

export const UNDER_WATCH_FLAG = "تحت المراقبة";
export const EXPLOSIVE_WATCH_FLAG = "تحت المراقبة - انفجار محتمل";
export const HIDDEN_ACCUM_FLAG = "تجميع مؤسسي خفي";

export interface UnderWatchRow {
  symbol: string;
  name: string;
  price: number | null;
  change_percent: number | null;
  volume: number | null;
  volume_ratio: number | null;
  net_flow: number | null;
  buy_ratio: number | null;
  flag: string;
  explosive: boolean;
  hidden_accumulation: boolean;
  compressed: boolean;
  upward: boolean;
  aggressive_buy: boolean;
  flow_spike: boolean;
  resistance_break: boolean;
  score: number;
  reasons: string[];
  updated_at: string | null;
}

export interface UnderWatchResponse {
  success: boolean;
  count: number;
  data: UnderWatchRow[];
  updated_at: string | null;
}

export async function fetchUnderWatch(): Promise<UnderWatchResponse> {
  const response = await apiFetch("/api/v1/watchlist/under-watch");
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    throw new Error(readError(payload, "تعذر جلب الشركات تحت المراقبة"));
  }
  return parseUnderWatch(payload);
}

export function parseUnderWatch(payload: Record<string, unknown> | null): UnderWatchResponse {
  const rows = Array.isArray(payload?.data) ? payload.data : [];
  return {
    success: Boolean(payload?.success ?? true),
    count: toFiniteNumber(payload?.count) ?? rows.length,
    data: rows
      .map((item) => parseUnderWatchRow(item))
      .filter((row): row is UnderWatchRow => row != null),
    updated_at: payload?.updated_at == null ? null : String(payload.updated_at),
  };
}

export function parseUnderWatchRow(raw: unknown): UnderWatchRow | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  if (!/^\d{4}$/.test(symbol)) return null;
  const explosive = Boolean(row.explosive);
  const hidden = Boolean(row.hidden_accumulation) || String(row.flag || "") === HIDDEN_ACCUM_FLAG;
  const flag = String(
    row.flag || (explosive ? EXPLOSIVE_WATCH_FLAG : hidden ? HIDDEN_ACCUM_FLAG : UNDER_WATCH_FLAG),
  );
  return {
    symbol,
    name: String(row.name ?? ""),
    price: toFiniteNumber(row.price),
    change_percent: toFiniteNumber(row.change_percent),
    volume: toFiniteNumber(row.volume),
    volume_ratio: toFiniteNumber(row.volume_ratio),
    net_flow: toFiniteNumber(row.net_flow),
    buy_ratio: toFiniteNumber(row.buy_ratio),
    flag,
    explosive,
    hidden_accumulation: hidden,
    compressed: Boolean(row.compressed),
    upward: Boolean(row.upward),
    aggressive_buy: Boolean(row.aggressive_buy),
    flow_spike: Boolean(row.flow_spike),
    resistance_break: Boolean(row.resistance_break),
    score: toFiniteNumber(row.score) ?? 0,
    reasons: Array.isArray(row.reasons) ? row.reasons.map(String) : [],
    updated_at: row.updated_at == null ? null : String(row.updated_at),
  };
}

function readError(payload: Record<string, unknown> | null, fallback: string): string {
  if (!payload) return fallback;
  if (typeof payload.message === "string" && payload.message.trim()) return payload.message;
  if (typeof payload.detail === "string" && payload.detail.trim()) return payload.detail;
  return fallback;
}
