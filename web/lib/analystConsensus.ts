import { isValidLongPlan } from "@/lib/tradeGeometry";
import { toFiniteNumber } from "@/lib/screener";

export interface AnalystPickRow {
  symbol: string;
  name: string;
  sector: string;
  houses: string[];
  analyst_count: number;
  consensus_strength: number;
  direction: "buy" | "exit";
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
  exit_count: number;
  data: AnalystPickRow[];
  exits: AnalystPickRow[];
}

function isExitPlan(entry: string, target: string, stop: string): boolean {
  const price = Number(entry);
  const targetPrice = Number(target);
  const stopPrice = Number(stop);
  return Number.isFinite(price) && Number.isFinite(targetPrice) && Number.isFinite(stopPrice) && targetPrice > 0 && targetPrice < price && price < stopPrice;
}

function parseRow(raw: unknown, direction: "buy" | "exit"): AnalystPickRow | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  const entry = String(row.entry_price ?? "");
  const target = String(row.target_price ?? "");
  const stop = String(row.stop_loss ?? "");
  const houses = Array.isArray(row.houses) ? row.houses.map((item) => String(item).trim()).filter(Boolean) : [];
  const note = String(row.note ?? "");
  const priced = entry !== "" || target !== "" || stop !== "";
  if (!/^\d{4}$/.test(symbol) || houses.length === 0) return null;
  if (direction === "buy" && !isValidLongPlan(entry, target, stop)) return null;
  if (direction === "exit" && priced && !isExitPlan(entry, target, stop)) return null;
  if (direction === "exit" && !priced && !note.trim()) return null;
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
    direction,
    published_on: String(row.published_on ?? ""),
    window_days: toFiniteNumber(row.window_days) ?? 0,
    last_price: toFiniteNumber(row.last_price),
    entry_price: moneyText(entry),
    entry_low: moneyText(entryLow),
    entry_high: moneyText(entryHigh),
    target_price: moneyText(target),
    target_low: moneyText(targetLow),
    target_high: moneyText(targetHigh),
    stop_loss: moneyText(stop),
    stop_low: moneyText(stopLow),
    stop_high: moneyText(stopHigh),
    reward_ratio: toFiniteNumber(row.reward_ratio) ?? 0,
    timeframe: String(row.timeframe ?? ""),
    valid_until: String(row.valid_until ?? ""),
    note: String(row.note ?? ""),
    shariah_status: row.shariah_status ? String(row.shariah_status) : null,
    shariah_label: String(row.shariah_label ?? ""),
  };
}

function moneyText(value: string): string {
  if (!value.trim()) return "";
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number.toFixed(2) : "";
}

export function parseAnalystConsensus(payload: unknown): AnalystConsensusResponse {
  const body = (payload && typeof payload === "object" ? payload : {}) as Record<string, unknown>;
  const data = Array.isArray(body.data) ? body.data.map((row) => parseRow(row, "buy")).filter((row): row is AnalystPickRow => row != null) : [];
  const exits = Array.isArray(body.exits) ? body.exits.map((row) => parseRow(row, "exit")).filter((row): row is AnalystPickRow => row != null) : [];
  return {
    success: body.success !== false,
    source: String(body.source ?? "curated"),
    count: data.length,
    as_of: String(body.as_of ?? ""),
    window_days: toFiniteNumber(body.window_days) ?? 0,
    hint: String(body.hint ?? ""),
    exit_count: exits.length,
    data,
    exits,
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
