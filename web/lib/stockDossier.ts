import { companyBySymbol } from "@/lib/marketData";
import { classifyShariah } from "@/lib/shariah";
import { TASI_COMPLIANCE_UNIVERSE, type ComplianceStatusLabel } from "@/prisma/tasiUniverse";

/** Mid-cycle earnings multiple used only as a labeled estimate, never as a traded price. */
const FAIR_PE = 15;

const BY_SYMBOL = new Map(TASI_COMPLIANCE_UNIVERSE.map((item) => [item.symbol, item]));

export interface TapeLiquidityInput {
  quote_mode?: "live" | "last_close" | "waiting";
  buy_ratio: number | null;
  volume_ratio?: number | null;
  block_trades?: number;
}

export type FieldState = "ready" | "updating" | "missing";
export type ValuationStance = "over" | "attractive" | "near" | "pending";
export type SessionPath = "up" | "down" | "unknown";

export interface DossierFundamentals {
  peRatio?: number | null;
  dividendYieldPct?: number | null;
  settled: boolean;
}

export interface StockDossier {
  symbol: string;
  shariah: ComplianceStatusLabel | null;
  peRatio: number | null;
  dividendYieldPct: number | null;
  /** Interest-bearing debt / market value from the screening book. Not debt-to-equity. */
  debtToMarket: number | null;
  /** Price × 15 / P/E. Null until both a price and a P/E exist. */
  fairValue: number | null;
  healthScore: number | null;
  liquidityScore: number | null;
  peState: FieldState;
  yieldState: FieldState;
  fairState: FieldState;
  liquidityState: FieldState;
  healthState: FieldState;
  debtState: FieldState;
}

export function buildStockDossier(
  symbol: string,
  livePrice: number | null,
  tape: TapeLiquidityInput | null,
  fundamentals?: DossierFundamentals | null,
): StockDossier {
  const ticker = symbol.trim().toUpperCase();
  const book = BY_SYMBOL.get(ticker);
  const market = companyBySymbol(ticker);
  const shariah = book ? classifyShariah(book) : null;
  const settled = fundamentals?.settled !== false;
  const peRatio = firstPositive(market?.pe_ratio, fundamentals?.peRatio);
  const dividendYieldPct = firstFinite(market?.dividend_yield, fundamentals?.dividendYieldPct);
  const debtToMarket = book ? finite(book.debtRatio) : null;
  const price = livePrice != null && livePrice > 0 ? livePrice : null;
  const fairValue = price != null && peRatio != null ? roundTo((price * FAIR_PE) / peRatio, 2) : null;
  const health = healthScore({ debtToMarket, peRatio, dividendYieldPct });
  const liquidity = liquidityScore(tape);

  return {
    symbol: ticker,
    shariah,
    peRatio,
    dividendYieldPct,
    debtToMarket,
    fairValue,
    healthScore: health,
    liquidityScore: liquidity,
    peState: fieldState(peRatio, settled && market?.pe_ratio == null),
    yieldState: fieldState(dividendYieldPct, settled && market?.dividend_yield == null),
    fairState: fairValue != null ? "ready" : peRatio == null && !settled ? "updating" : "missing",
    liquidityState: liquidity != null ? "ready" : tape?.quote_mode === "live" ? "missing" : "updating",
    healthState: health != null ? "ready" : peRatio == null && dividendYieldPct == null && !settled ? "updating" : "missing",
    debtState: debtToMarket != null ? "ready" : "missing",
  };
}

/** Session VWAP is the volume-weighted price. Equal or above is the upward path. */
export function sessionPath(price: number | null, vwap: number | null): SessionPath {
  if (price == null || vwap == null || price <= 0 || vwap <= 0 || !Number.isFinite(price) || !Number.isFinite(vwap)) {
    return "unknown";
  }
  return price >= vwap ? "up" : "down";
}

/** Premium above 5% is stretched. At or below fair value is the attractive zone. */
export function valuationStance(price: number | null, fairValue: number | null): ValuationStance {
  if (price == null || price <= 0 || fairValue == null || fairValue <= 0) return "pending";
  const gap = (price - fairValue) / fairValue;
  if (gap > 0.05) return "over";
  if (gap <= 0) return "attractive";
  return "near";
}

function fieldState(value: number | null, settledWithoutLocal: boolean): FieldState {
  if (value != null) return "ready";
  return settledWithoutLocal ? "missing" : "updating";
}

function firstPositive(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    const number = positive(value);
    if (number != null) return number;
  }
  return null;
}

function firstFinite(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    const number = finite(value);
    if (number != null) return number;
  }
  return null;
}

function healthScore(input: {
  debtToMarket: number | null;
  peRatio: number | null;
  dividendYieldPct: number | null;
}): number | null {
  const pillars: { weight: number; score: number }[] = [];
  if (input.debtToMarket != null) {
    pillars.push({ weight: 0.35, score: clamp(100 - input.debtToMarket * 150) });
  }
  if (input.peRatio != null) {
    pillars.push({ weight: 0.35, score: clamp(100 - Math.abs(input.peRatio - 13) * 5.5) });
  }
  if (input.dividendYieldPct != null) {
    pillars.push({ weight: 0.3, score: clamp((input.dividendYieldPct / 6) * 100) });
  }
  if (!pillars.length) return null;
  const weight = pillars.reduce((sum, pillar) => sum + pillar.weight, 0);
  const total = pillars.reduce((sum, pillar) => sum + pillar.weight * pillar.score, 0);
  return roundTo(total / weight, 1);
}

/** Live tape only. A volume spike without block prints cannot fill the block pillar. */
export function liquidityScore(tape: TapeLiquidityInput | null): number | null {
  if (!tape || tape.quote_mode !== "live") return null;
  const buy = finite(tape.buy_ratio);
  if (buy == null) return null;
  const volume = finite(tape.volume_ratio);
  const blocks = finite(tape.block_trades) ?? 0;
  const buyScore = clamp(buy * 100);
  const volumeScore = volume == null ? 40 : clamp(40 + (volume - 1) * 30);
  const blockScore = clamp((Math.min(blocks, 5) / 5) * 100);
  return roundTo(buyScore * 0.45 + volumeScore * 0.35 + blockScore * 0.2, 1);
}

function positive(value: number | null | undefined): number | null {
  const number = finite(value);
  return number != null && number > 0 ? number : null;
}

function finite(value: number | null | undefined): number | null {
  return value != null && Number.isFinite(value) ? value : null;
}

function clamp(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

function roundTo(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}
