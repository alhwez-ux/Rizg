import { isValidLongPlan } from "@/lib/tradeGeometry";
import { toFiniteNumber } from "@/lib/screener";

export interface DailyOpportunityRow {
  symbol: string;
  name: string;
  sector: string;
  last_price: number | null;
  entry_price: string;
  target_price: string;
  stop_loss: string;
  reward_ratio: number;
  timeframe: string;
  setup: string;
  reason: string;
  score: number;
  entry_locked_at: string | null;
  shariah_status: string | null;
  shariah_label: string;
}

export interface DailyOpportunitiesResponse {
  success: boolean;
  session_phase: string;
  session_label: string;
  source: string;
  count: number;
  min_reward_ratio: number;
  hint: string;
  scanned_at: string;
  data: DailyOpportunityRow[];
}

function parseRow(raw: unknown): DailyOpportunityRow | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  const entry = String(row.entry_price ?? "");
  const target = String(row.target_price ?? "");
  const stop = String(row.stop_loss ?? "");
  if (!/^\d{4}$/.test(symbol) || !isValidLongPlan(entry, target, stop)) return null;
  const reward = toFiniteNumber(row.reward_ratio) ?? 0;
  if (reward < 1.5) return null;
  return {
    symbol,
    name: String(row.name ?? symbol),
    sector: String(row.sector ?? ""),
    last_price: toFiniteNumber(row.last_price),
    entry_price: Number(entry).toFixed(2),
    target_price: Number(target).toFixed(2),
    stop_loss: Number(stop).toFixed(2),
    reward_ratio: reward,
    timeframe: String(row.timeframe ?? "جلسة اليوم"),
    setup: String(row.setup ?? ""),
    reason: String(row.reason ?? ""),
    score: toFiniteNumber(row.score) ?? 0,
    entry_locked_at: row.entry_locked_at ? String(row.entry_locked_at) : null,
    shariah_status: row.shariah_status ? String(row.shariah_status) : null,
    shariah_label: String(row.shariah_label ?? ""),
  };
}

export function parseDailyOpportunities(payload: unknown): DailyOpportunitiesResponse {
  const body = (payload && typeof payload === "object" ? payload : {}) as Record<string, unknown>;
  const data = Array.isArray(body.data) ? body.data.map(parseRow).filter((row): row is DailyOpportunityRow => row != null) : [];
  return {
    success: body.success !== false,
    session_phase: String(body.session_phase ?? ""),
    session_label: String(body.session_label ?? ""),
    source: String(body.source ?? ""),
    count: data.length,
    min_reward_ratio: toFiniteNumber(body.min_reward_ratio) ?? 1.5,
    hint: String(body.hint ?? ""),
    scanned_at: String(body.scanned_at ?? ""),
    data,
  };
}

export async function fetchDailyOpportunities(pureOnly = false): Promise<DailyOpportunitiesResponse> {
  const query = pureOnly ? "?pure_only=true" : "";
  const response = await fetch(`/api/opportunities/daily${query}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error("تعذر جلب فرص رزق اليومية");
  }
  return parseDailyOpportunities(await response.json());
}
