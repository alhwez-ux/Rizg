import { apiFetch } from "@/lib/api";
import { toFiniteNumber } from "@/lib/screener";

export type PreOpenSignalKind = "accumulation" | "distribution" | "balanced";
export type PreOpenLiquidityState = "تجميع" | "تصريف" | "توازن";
export type PreOpenBlockSide = "buy" | "sell" | "mixed";

export interface PreOpenRow {
  symbol: string;
  name: string;
  sector: string;
  expected_open: number | null;
  prev_close: number | null;
  open_variation_pct: number | null;
  buy_volume: number;
  sell_volume: number;
  book_imbalance: number | null;
  buy_share: number | null;
  block_trades: number;
  last_block_value: number | null;
  large_block_side: PreOpenBlockSide | null;
  signal: string;
  signal_kind: PreOpenSignalKind;
  liquidity_state: PreOpenLiquidityState;
  score: number;
}

export interface PreOpenScanResponse {
  success: boolean;
  session_phase: string;
  session_label: string;
  in_window: boolean;
  window_start: string;
  window_end: string;
  timezone: string;
  source: string;
  count: number;
  accumulation_count: number;
  distribution_count: number;
  hint: string;
  scanned_at: string;
  data: PreOpenRow[];
}

const EMPTY: PreOpenScanResponse = {
  success: true,
  session_phase: "closed",
  session_label: "",
  in_window: false,
  window_start: "09:30",
  window_end: "10:00",
  timezone: "Asia/Riyadh",
  source: "TickChart",
  count: 0,
  accumulation_count: 0,
  distribution_count: 0,
  hint: "",
  scanned_at: "",
  data: [],
};

function parseBlockSide(value: unknown): PreOpenBlockSide | null {
  if (value === "buy" || value === "sell" || value === "mixed") return value;
  return null;
}

function parseKind(value: unknown): PreOpenSignalKind {
  if (value === "accumulation" || value === "distribution" || value === "balanced") return value;
  return "balanced";
}

function parseState(value: unknown): PreOpenLiquidityState {
  if (value === "تجميع" || value === "تصريف" || value === "توازن") return value;
  return "توازن";
}

export function parsePreOpenRow(raw: unknown): PreOpenRow | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  if (!/^\d{4}$/.test(symbol)) return null;
  return {
    symbol,
    name: String(row.name ?? symbol),
    sector: String(row.sector ?? ""),
    expected_open: toFiniteNumber(row.expected_open),
    prev_close: toFiniteNumber(row.prev_close),
    open_variation_pct: toFiniteNumber(row.open_variation_pct),
    buy_volume: toFiniteNumber(row.buy_volume) ?? 0,
    sell_volume: toFiniteNumber(row.sell_volume) ?? 0,
    book_imbalance: toFiniteNumber(row.book_imbalance),
    buy_share: toFiniteNumber(row.buy_share),
    block_trades: Math.max(0, Math.round(toFiniteNumber(row.block_trades) ?? 0)),
    last_block_value: toFiniteNumber(row.last_block_value),
    large_block_side: parseBlockSide(row.large_block_side),
    signal: String(row.signal ?? ""),
    signal_kind: parseKind(row.signal_kind),
    liquidity_state: parseState(row.liquidity_state),
    score: toFiniteNumber(row.score) ?? 0,
  };
}

export function parsePreOpenScan(payload: Record<string, unknown> | null): PreOpenScanResponse {
  const rows = Array.isArray(payload?.data) ? payload.data : [];
  const data = rows.map(parsePreOpenRow).filter((row): row is PreOpenRow => row != null);
  return {
    success: Boolean(payload?.success ?? true),
    session_phase: String(payload?.session_phase ?? ""),
    session_label: String(payload?.session_label ?? ""),
    in_window: Boolean(payload?.in_window),
    window_start: String(payload?.window_start ?? "09:30"),
    window_end: String(payload?.window_end ?? "10:00"),
    timezone: String(payload?.timezone ?? "Asia/Riyadh"),
    source: String(payload?.source ?? "TickChart"),
    count: toFiniteNumber(payload?.count) ?? data.length,
    accumulation_count: toFiniteNumber(payload?.accumulation_count) ?? data.filter((row) => row.signal_kind === "accumulation").length,
    distribution_count: toFiniteNumber(payload?.distribution_count) ?? data.filter((row) => row.signal_kind === "distribution").length,
    hint: String(payload?.hint ?? ""),
    scanned_at: payload?.scanned_at == null ? "" : String(payload.scanned_at),
    data,
  };
}

function readError(payload: Record<string, unknown> | null, fallback: string): string {
  if (!payload) return fallback;
  if (typeof payload.message === "string" && payload.message.trim()) return payload.message;
  if (typeof payload.detail === "string" && payload.detail.trim()) return payload.detail;
  return fallback;
}

export async function fetchPreOpenScan(): Promise<PreOpenScanResponse> {
  const response = await apiFetch("/api/v1/preopen/scan", { timeoutMs: 45_000 });
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    throw new Error(readError(payload, "تعذر جلب قراءة ماقبل الافتتاح"));
  }
  return parsePreOpenScan(payload);
}

export function buySharePercent(row: Pick<PreOpenRow, "buy_volume" | "sell_volume" | "buy_share">): number {
  if (row.buy_share != null && Number.isFinite(row.buy_share)) {
    return Math.max(0, Math.min(100, row.buy_share * 100));
  }
  const total = row.buy_volume + row.sell_volume;
  if (total <= 0) return 50;
  return Math.max(0, Math.min(100, (row.buy_volume / total) * 100));
}

export { EMPTY as EMPTY_PREOPEN_SCAN };
