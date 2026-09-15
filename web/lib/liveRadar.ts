import { apiFetch } from "@/lib/api";
import type { LiquidityTick } from "@/lib/liquidity";
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
  bid?: number | null;
  ask?: number | null;
  spread?: number | null;
  bid_size?: number | null;
  ask_size?: number | null;
  book_pressure?: number | null;
  quote_mode?: "live" | "last_close" | "waiting";
  session_phase?: string;
  session_label?: string;
  live_quote?: boolean;
  mfi?: number | null;
  institutional_mfi?: number | null;
  retail_mfi?: number | null;
  volume_ratio?: number | null;
  block_trades?: number;
  bid_wall?: { price: number; quantity: number } | null;
  ask_wall?: { price: number; quantity: number } | null;
}

export interface LiveRadarResponse {
  symbol: string;
  success: boolean;
  source: string;
  analysis: LiveRadarReport;
}

export async function fetchLiveRadar(symbol: string, _interval = "1d"): Promise<LiveRadarResponse | null> {
  const ticker = symbol.trim();
  if (!ticker) return null;
  const response = await apiFetch(`/api/v1/radar/live/${encodeURIComponent(ticker)}`);
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    if (response.status === 404) {
      return {
        symbol: ticker,
        success: true,
        source: "TickChart",
        analysis: {
          symbol: ticker,
          signal: "neutral",
          entry: false,
          exit: false,
          trap: null,
          flow_verified: false,
          score: 0,
          net_flow: 0,
          inflow: 0,
          outflow: 0,
          buy_volume: 0,
          sell_volume: 0,
          buy_ratio: null,
          sell_ratio: null,
          last_price: null,
          vwap: null,
          atr: null,
          suggested_entry: null,
          suggested_exit: null,
          target_price: null,
          stop_loss: null,
          change_percent: null,
          trade_count: 0,
          reasons: ["في انتظار بيانات الجلسة"],
          quote_mode: "waiting",
        },
      };
    }
    throw new Error(readApiError(payload, "تعذر جلب رادار السيولة من تكرتشارت"));
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
    source: String(payload?.source ?? "TickChart"),
    analysis,
  };
}

export function overlayTickOnReport(report: LiveRadarReport, tick: LiquidityTick | null): LiveRadarReport {
  if (!tick || tick.symbol.toUpperCase() !== report.symbol.toUpperCase()) {
    return report;
  }
    return {
    ...report,
    last_price: tick.lastPrice ?? report.last_price,
    net_flow: tick.netFlow || report.net_flow,
    inflow: tick.inflow || report.inflow,
    outflow: tick.outflow || report.outflow,
    buy_volume: tick.buyVolume || report.buy_volume,
    sell_volume: tick.sellVolume || report.sell_volume,
    trade_count: tick.tradeCount || report.trade_count,
  };
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
    bid: toFiniteNumber(row.bid),
    ask: toFiniteNumber(row.ask),
    spread: toFiniteNumber(row.spread),
    bid_size: toFiniteNumber(row.bid_size),
    ask_size: toFiniteNumber(row.ask_size),
    book_pressure: toFiniteNumber(row.book_pressure),
    live_quote: Boolean(row.live_quote),
    quote_mode:
      row.quote_mode === "live" || row.quote_mode === "last_close" || row.quote_mode === "waiting"
        ? row.quote_mode
        : row.live_quote
          ? "live"
          : row.last_price
            ? "last_close"
            : "waiting",
    session_phase: row.session_phase ? String(row.session_phase) : undefined,
    session_label: row.session_label ? String(row.session_label) : undefined,
    mfi: toFiniteNumber(row.mfi),
    institutional_mfi: toFiniteNumber(row.institutional_mfi),
    retail_mfi: toFiniteNumber(row.retail_mfi),
    volume_ratio: toFiniteNumber(row.volume_ratio),
    block_trades: toFiniteNumber(row.block_trades) ?? 0,
    bid_wall: parseWall(row.bid_wall),
    ask_wall: parseWall(row.ask_wall),
  };
}

function parseWall(raw: unknown): { price: number; quantity: number } | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const price = toFiniteNumber(row.price);
  const quantity = toFiniteNumber(row.quantity);
  if (price == null || quantity == null) return null;
  return { price, quantity };
}

function readApiError(payload: Record<string, unknown> | null, fallback: string): string {
  if (!payload) return fallback;
  const message = payload.message;
  if (typeof message === "string" && message.trim()) return message;
  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return fallback;
}
