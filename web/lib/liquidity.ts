export type ConnectionStatus = "connecting" | "live" | "reconnecting" | "offline";

export type TapeRegime = "accumulation" | "distribution" | "neutral";

export interface LiquidityTick {
  type: string;
  symbol: string;
  netFlow: number;
  inflow: number;
  outflow: number;
  buyVolume: number;
  sellVolume: number;
  lastPrice: number | null;
  lastSide: "BUY" | "SELL" | null;
  tick: string | null;
  side: "BUY" | "SELL" | null;
  price: number | null;
  volume: number | null;
  moneyFlow: number | null;
  tradeCount: number;
  timestamp: string | null;
}

export interface LiquidityStreamPayload {
  type?: string;
  symbol?: string;
  net_flow?: string | number;
  inflow?: string | number;
  outflow?: string | number;
  buy_volume?: string | number;
  sell_volume?: string | number;
  last_price?: string | number | null;
  last_side?: "BUY" | "SELL" | null;
  tick?: string | null;
  side?: "BUY" | "SELL" | null;
  price?: string | number | null;
  volume?: string | number | null;
  money_flow?: string | number | null;
  trade_count?: number;
  timestamp?: string | null;
}

const SPARKLINE_POINTS = 48;

export function toNumber(value: string | number | null | undefined): number {
  if (value == null || value === "") return 0;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function parseTick(payload: LiquidityStreamPayload): LiquidityTick | null {
  if (
    payload.type === "ping" ||
    payload.type === "pong" ||
    payload.type === "error" ||
    payload.type === "alert"
  ) {
    return null;
  }
  if (payload.net_flow == null && payload.buy_volume == null) {
    return null;
  }

  return {
    type: payload.type ?? "liquidity",
    symbol: payload.symbol ?? "4030",
    netFlow: toNumber(payload.net_flow),
    inflow: toNumber(payload.inflow),
    outflow: toNumber(payload.outflow),
    buyVolume: toNumber(payload.buy_volume),
    sellVolume: toNumber(payload.sell_volume),
    lastPrice: payload.last_price == null ? null : toNumber(payload.last_price),
    lastSide: payload.last_side ?? null,
    tick: payload.tick ?? null,
    side: payload.side ?? null,
    price: payload.price == null ? null : toNumber(payload.price),
    volume: payload.volume == null ? null : toNumber(payload.volume),
    moneyFlow: payload.money_flow == null ? null : toNumber(payload.money_flow),
    tradeCount: payload.trade_count ?? 0,
    timestamp: payload.timestamp ?? null,
  };
}

export function regimeFromNetFlow(netFlow: number): TapeRegime {
  if (netFlow > 0) return "accumulation";
  if (netFlow < 0) return "distribution";
  return "neutral";
}

export function formatCompact(value: number, digits = 2): string {
  return value.toLocaleString("ar-SA", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    numberingSystem: "latn",
  });
}

export function formatMoney(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : value > 0 ? "+" : "";
  if (abs >= 1_000_000_000) return `${sign}${formatCompact(abs / 1_000_000_000)} مليار`;
  if (abs >= 1_000_000) return `${sign}${formatCompact(abs / 1_000_000)} مليون`;
  if (abs >= 1_000) return `${sign}${formatCompact(abs / 1_000)} ألف`;
  return `${sign}${formatCompact(abs)}`;
}

export function formatVolume(value: number): string {
  if (value >= 1_000_000) return `${formatCompact(value / 1_000_000)} مليون`;
  if (value >= 1_000) return `${formatCompact(value / 1_000)} ألف`;
  return value.toLocaleString("ar-SA", {
    maximumFractionDigits: 0,
    numberingSystem: "latn",
  });
}

export function formatPrice(value: number | null): string {
  if (value == null) return "—";
  return formatCompact(value);
}

export function formatCount(value: number): string {
  return value.toLocaleString("ar-SA", {
    maximumFractionDigits: 0,
    numberingSystem: "latn",
  });
}

export function pushSparkline(history: number[], value: number): number[] {
  if (history.length >= SPARKLINE_POINTS) {
    return [...history.slice(1), value];
  }
  return [...history, value];
}

export const DEFAULT_WS_URL =
  process.env.NEXT_PUBLIC_LIQUIDITY_WS_URL ?? "ws://localhost:8000/ws/liquidity/4030";

export const DEFAULT_SYMBOL = process.env.NEXT_PUBLIC_LIQUIDITY_SYMBOL ?? "4030";

export type AlertKind =
  | "inflow_surge"
  | "volume_surge"
  | "net_flow_spike"
  | "outflow_surge";

export interface LiquidityAlertEvent {
  type: "alert";
  id: string;
  symbol: string;
  kind: AlertKind;
  title: string;
  message: string;
  windowSeconds: number;
  windowInflow: number;
  windowVolume: number;
  windowNetFlow: number;
  lastPrice: number | null;
  timestamp: string;
}

export interface AlertStreamPayload {
  type?: string;
  id?: string;
  symbol?: string;
  kind?: AlertKind;
  title?: string;
  message?: string;
  window_seconds?: number;
  window_inflow?: string | number;
  window_volume?: string | number;
  window_net_flow?: string | number;
  last_price?: string | number | null;
  timestamp?: string;
}

export function parseAlert(payload: AlertStreamPayload): LiquidityAlertEvent | null {
  if (payload.type !== "alert" || !payload.id) return null;
  return {
    type: "alert",
    id: payload.id,
    symbol: payload.symbol ?? "4030",
    kind: payload.kind ?? "inflow_surge",
    title: payload.title ?? "",
    message: payload.message ?? "",
    windowSeconds: payload.window_seconds ?? 60,
    windowInflow: toNumber(payload.window_inflow),
    windowVolume: toNumber(payload.window_volume),
    windowNetFlow: toNumber(payload.window_net_flow),
    lastPrice: payload.last_price == null ? null : toNumber(payload.last_price),
    timestamp: payload.timestamp ?? new Date().toISOString(),
  };
}

export function formatPercent(value: number | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${formatCompact(Math.abs(value), digits)}%`;
}

export function formatRatio(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${formatCompact(value * 100, 0)}%`;
}

export function formatClock(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("ar-SA", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    numberingSystem: "latn",
  });
}
