import { isValidLongPlan } from "@/lib/tradeGeometry";
import { toFiniteNumber } from "@/lib/screener";

export interface AnalystPickRow {
  symbol: string;
  name: string;
  sector: string;
  houses: string[];
  last_price: number | null;
  entry_price: string;
  target_price: string;
  stop_loss: string;
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
  return {
    symbol,
    name: String(row.name ?? symbol),
    sector: String(row.sector ?? ""),
    houses,
    last_price: toFiniteNumber(row.last_price),
    entry_price: Number(entry).toFixed(2),
    target_price: Number(target).toFixed(2),
    stop_loss: Number(stop).toFixed(2),
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
    hint: String(body.hint ?? ""),
    data,
  };
}

export async function fetchAnalystConsensus(pureOnly = false): Promise<AnalystConsensusResponse> {
  const query = pureOnly ? "?pure_only=true" : "";
  const response = await fetch(`/api/analysts/consensus${query}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error("تعذر جلب عيون بيوت الخبرة");
  }
  return parseAnalystConsensus(await response.json());
}
