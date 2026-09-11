export type SignalKind = "entry" | "exit" | "none";

export interface ScreenerRow {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume: number;
  value: number;
  inflow: number;
  outflow: number;
  net_flow: number;
  buy_volume: number;
  sell_volume: number;
  buy_ratio: number | null;
  sell_ratio: number | null;
  volume_surge: number | null;
  score: number;
  entry_signal: boolean;
  exit_signal: boolean;
  unexpected: boolean;
  flow_verified: boolean;
  tracked: boolean;
  vwap: number | null;
  atr: number | null;
  bid: number | null;
  ask: number | null;
  book_pressure: number | null;
  suggested_entry: number | null;
  suggested_exit: number | null;
  target_price: number | null;
  stop_loss: number | null;
  reasons: string[];
  sources: string[];
  updated_at: string | null;
}

export interface MarketPulse {
  index: string;
  index_value: number | null;
  index_change_percent: number | null;
  advancing: number | null;
  declining: number | null;
  delayed: boolean;
}

export interface ScreenerSnapshot {
  watchlist: ScreenerRow[];
  radar: ScreenerRow[];
  pulse: MarketPulse;
  scanned: number;
  delayed: boolean;
  updated_at: string | null;
}

export function signalKind(row: Pick<ScreenerRow, "entry_signal" | "exit_signal">): SignalKind {
  if (row.entry_signal) return "entry";
  if (row.exit_signal) return "exit";
  return "none";
}

export function signalKey(row: ScreenerRow): string {
  return `${row.symbol}:${row.entry_signal ? "e" : ""}${row.exit_signal ? "x" : ""}:${row.suggested_entry ?? ""}:${row.suggested_exit ?? ""}`;
}

export function toFiniteNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function parseRow(raw: Record<string, unknown>): ScreenerRow {
  return {
    symbol: String(raw.symbol ?? ""),
    name: String(raw.name ?? ""),
    price: toFiniteNumber(raw.price) ?? 0,
    change_percent: toFiniteNumber(raw.change_percent) ?? 0,
    volume: toFiniteNumber(raw.volume) ?? 0,
    value: toFiniteNumber(raw.value) ?? 0,
    inflow: toFiniteNumber(raw.inflow) ?? 0,
    outflow: toFiniteNumber(raw.outflow) ?? 0,
    net_flow: toFiniteNumber(raw.net_flow) ?? 0,
    buy_volume: toFiniteNumber(raw.buy_volume) ?? 0,
    sell_volume: toFiniteNumber(raw.sell_volume) ?? 0,
    buy_ratio: toFiniteNumber(raw.buy_ratio),
    sell_ratio: toFiniteNumber(raw.sell_ratio),
    volume_surge: toFiniteNumber(raw.volume_surge),
    score: toFiniteNumber(raw.score) ?? 0,
    entry_signal: Boolean(raw.entry_signal),
    exit_signal: Boolean(raw.exit_signal),
    unexpected: Boolean(raw.unexpected),
    flow_verified: Boolean(raw.flow_verified),
    tracked: Boolean(raw.tracked),
    vwap: toFiniteNumber(raw.vwap),
    atr: toFiniteNumber(raw.atr),
    bid: toFiniteNumber(raw.bid),
    ask: toFiniteNumber(raw.ask),
    book_pressure: toFiniteNumber(raw.book_pressure),
    suggested_entry: toFiniteNumber(raw.suggested_entry),
    suggested_exit: toFiniteNumber(raw.suggested_exit),
    target_price: toFiniteNumber(raw.target_price),
    stop_loss: toFiniteNumber(raw.stop_loss),
    reasons: Array.isArray(raw.reasons) ? raw.reasons.map(String) : [],
    sources: Array.isArray(raw.sources) ? raw.sources.map(String) : [],
    updated_at: raw.updated_at == null ? null : String(raw.updated_at),
  };
}
