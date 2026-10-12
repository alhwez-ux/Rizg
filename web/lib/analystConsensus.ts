import { isValidLongPlan } from "@/lib/tradeGeometry";
import { toFiniteNumber } from "@/lib/screener";

export interface AnalystPickRow {
  symbol: string;
  name: string;
  sector: string;
  houses: string[];
  analyst_count: number;
  consensus_strength: number;
  published_on: string;
  window_days: number;
  last_price: number | null;
  entry_price: string;
  entry_low: string;
  entry_high: string;
  target_price: string;
  target_low: string;
  target_high: string;
  stop_loss: string;
  stop_low: string;
  stop_high: string;
  reward_ratio: number;
  timeframe: string;
  valid_until: string;
  note: string;
  shariah_status: string | null;
  shariah_label: string;
}

export interface AnalystConsensusResponse {
  success: boolean;
  source: string;
  count: number;
  as_of: string;
  window_days: number;
  hint: string;
  data: AnalystPickRow[];
}

function parseRow(raw: unknown): AnalystPickRow | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  const entry = String(row.entry_price ?? "");
  const target = String(row.target_price ?? "");
  const stop = String(row.stop_loss ?? "");
  const houses = Array.isArray(row.houses) ? row.houses.map((item) => String(item).trim()).filter(Boolean) : [];
  if (!/^\d{4}$/.test(symbol) || houses.length === 0 || !isValidLongPlan(entry, target, stop)) return null;
  const entryLow = String(row.entry_low ?? entry);
  const entryHigh = String(row.entry_high ?? entry);
  const targetLow = String(row.target_low ?? target);
  const targetHigh = String(row.target_high ?? target);
  const stopLow = String(row.stop_low ?? stop);
  const stopHigh = String(row.stop_high ?? stop);
  return {
    symbol,
    name: String(row.name ?? symbol),
    sector: String(row.sector ?? ""),
    houses,
    analyst_count: toFiniteNumber(row.analyst_count) ?? houses.length,
    consensus_strength: toFiniteNumber(row.consensus_strength) ?? houses.length,
    published_on: String(row.published_on ?? ""),
    window_days: toFiniteNumber(row.window_days) ?? 0,
    last_price: toFiniteNumber(row.last_price),
    entry_price: Number(entry).toFixed(2),
    entry_low: Number(entryLow).toFixed(2),
    entry_high: Number(entryHigh).toFixed(2),
    target_price: Number(target).toFixed(2),
    target_low: Number(targetLow).toFixed(2),
    target_high: Number(targetHigh).toFixed(2),
    stop_loss: Number(stop).toFixed(2),
    stop_low: Number(stopLow).toFixed(2),
    stop_high: Number(stopHigh).toFixed(2),
    reward_ratio: toFiniteNumber(row.reward_ratio) ?? 0,
    timeframe: String(row.timeframe ?? ""),
    valid_until: String(row.valid_until ?? ""),
    note: String(row.note ?? ""),
    shariah_status: row.shariah_status ? String(row.shariah_status) : null,
    shariah_label: String(row.shariah_label ?? ""),
  };
}

export function parseAnalystConsensus(payload: unknown): AnalystConsensusResponse {
  const body = (payload && typeof payload === "object" ? payload : {}) as Record<string, unknown>;
  const data = Array.isArray(body.data) ? body.data.map(parseRow).filter((row): row is AnalystPickRow => row != null) : [];
  return {
    success: body.success !== false,
    source: String(body.source ?? "curated"),
    count: data.length,
    as_of: String(body.as_of ?? ""),
    window_days: toFiniteNumber(body.window_days) ?? 0,
    hint: String(body.hint ?? ""),
    data,
  };
}

export async function fetchAnalystConsensus(pureOnly = false, windowDays = 0): Promise<AnalystConsensusResponse> {
  const params = new URLSearchParams();
  if (pureOnly) params.set("pure_only", "true");
  if (windowDays > 0) params.set("window_days", String(windowDays));
  const query = params.size ? `?${params.toString()}` : "";
  const response = await fetch(`/api/analysts/consensus${query}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(windowDays > 0 ? "تعذر جلب شركات المحللين" : "تعذر جلب عيون بيوت الخبرة");
  }
  return parseAnalystConsensus(await response.json());
}
