import { apiFetch } from "@/lib/api";
import { toFiniteNumber } from "@/lib/screener";

export type SmartMoneyKind = "accumulation" | "distribution" | "watch";

export interface SmartMoneyRow {
  symbol: string;
  name: string;
  sector: string;
  last_price: number | null;
  institutional_flow_score: number;
  inst_share_pct: number;
  retail_share_pct: number;
  institutional_mfi: number | null;
  retail_mfi: number | null;
  block_trades: number;
  last_block_value: number | null;
  clustered: number;
  clustered_buys: number;
  cluster_run: number;
  near_bid_wall: boolean;
  signal: string;
  signal_kind: SmartMoneyKind;
  badge: string;
  reason: string;
  entry: number | null;
  target: number | null;
  stop: number | null;
  plan_ok: boolean;
  score: number;
}

export interface SmartMoneyScanResponse {
  success: boolean;
  session_phase: string;
  session_label: string;
  source: string;
  count: number;
  accumulation_count: number;
  distribution_count: number;
  watch_count: number;
  hint: string;
  scanned_at: string;
  data: SmartMoneyRow[];
}

const EMPTY: SmartMoneyScanResponse = {
  success: true,
  session_phase: "closed",
  session_label: "",
  source: "TickChart",
  count: 0,
  accumulation_count: 0,
  distribution_count: 0,
  watch_count: 0,
  hint: "",
  scanned_at: "",
  data: [],
};

function parseKind(value: unknown): SmartMoneyKind {
  if (value === "accumulation" || value === "distribution" || value === "watch") return value;
  return "watch";
}

export function parseSmartMoneyRow(raw: unknown): SmartMoneyRow | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  if (!/^\d{4}$/.test(symbol)) return null;
  return {
    symbol,
    name: String(row.name ?? symbol),
    sector: String(row.sector ?? ""),
    last_price: toFiniteNumber(row.last_price),
    institutional_flow_score: toFiniteNumber(row.institutional_flow_score) ?? toFiniteNumber(row.score) ?? 0,
    inst_share_pct: toFiniteNumber(row.inst_share_pct) ?? 0,
    retail_share_pct: toFiniteNumber(row.retail_share_pct) ?? 0,
    institutional_mfi: toFiniteNumber(row.institutional_mfi),
    retail_mfi: toFiniteNumber(row.retail_mfi),
    block_trades: Math.max(0, Math.round(toFiniteNumber(row.block_trades) ?? 0)),
    last_block_value: toFiniteNumber(row.last_block_value),
    clustered: Math.max(0, Math.round(toFiniteNumber(row.clustered) ?? 0)),
    clustered_buys: Math.max(0, Math.round(toFiniteNumber(row.clustered_buys) ?? 0)),
    cluster_run: Math.max(0, Math.round(toFiniteNumber(row.cluster_run) ?? 0)),
    near_bid_wall: Boolean(row.near_bid_wall),
    signal: String(row.signal ?? ""),
    signal_kind: parseKind(row.signal_kind),
    badge: String(row.badge ?? ""),
    reason: String(row.reason ?? ""),
    entry: toFiniteNumber(row.entry),
    target: toFiniteNumber(row.target),
    stop: toFiniteNumber(row.stop),
    plan_ok: Boolean(row.plan_ok),
    score: toFiniteNumber(row.score) ?? toFiniteNumber(row.institutional_flow_score) ?? 0,
  };
}

export function parseSmartMoneyScan(payload: Record<string, unknown> | null): SmartMoneyScanResponse {
  const rows = Array.isArray(payload?.data) ? payload.data : [];
  const data = rows.map(parseSmartMoneyRow).filter((row): row is SmartMoneyRow => row != null);
  return {
    success: Boolean(payload?.success ?? true),
    session_phase: String(payload?.session_phase ?? ""),
    session_label: String(payload?.session_label ?? ""),
    source: String(payload?.source ?? "TickChart"),
    count: toFiniteNumber(payload?.count) ?? data.length,
    accumulation_count: toFiniteNumber(payload?.accumulation_count) ?? data.filter((row) => row.signal_kind === "accumulation").length,
    distribution_count: toFiniteNumber(payload?.distribution_count) ?? data.filter((row) => row.signal_kind === "distribution").length,
    watch_count: toFiniteNumber(payload?.watch_count) ?? data.filter((row) => row.signal_kind === "watch").length,
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

export async function fetchSmartMoneyScan(): Promise<SmartMoneyScanResponse> {
  const response = await apiFetch("/api/v1/smart-money/scan", { timeoutMs: 45_000 });
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    throw new Error(readError(payload, "تعذر جلب رادار الصناديق"));
  }
  return parseSmartMoneyScan(payload);
}

export { EMPTY as EMPTY_SMART_MONEY_SCAN };
