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

export interface StockDossier {
  symbol: string;
  shariah: ComplianceStatusLabel | null;
  peRatio: number | null;
  dividendYieldPct: number | null;
  /** Interest-bearing debt / market value from the screening book. Not debt-to-equity. */
  debtToMarket: number | null;
  /** Live-price estimate. Null until a matching tick exists. */
  fairValue: number | null;
  healthScore: number | null;
  liquidityScore: number | null;
}

export function buildStockDossier(
  symbol: string,
  livePrice: number | null,
  tape: TapeLiquidityInput | null,
): StockDossier {
  const ticker = symbol.trim().toUpperCase();
  const book = BY_SYMBOL.get(ticker);
  const market = companyBySymbol(ticker);
  const shariah = book ? classifyShariah(book) : null;
  const peRatio = positive(market?.pe_ratio);
  const dividendYieldPct = finite(market?.dividend_yield);
  const debtToMarket = book ? finite(book.debtRatio) : null;
  const fairValue =
    livePrice != null && livePrice > 0 && peRatio != null ? roundTo((livePrice * FAIR_PE) / peRatio, 2) : null;

  return {
    symbol: ticker,
    shariah,
    peRatio,
    dividendYieldPct,
    debtToMarket,
    fairValue,
    healthScore: healthScore({ debtToMarket, peRatio, dividendYieldPct }),
    liquidityScore: liquidityScore(tape),
  };
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
