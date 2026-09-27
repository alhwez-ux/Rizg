import type { LiquidityTick } from "@/lib/liquidity";

/** The only price the radar may show: the live tick for this symbol. */
export function authoritativeTickPrice(symbol: string, tick: LiquidityTick | null): number | null {
  if (!tick) return null;
  if (tick.symbol.trim().toUpperCase() !== symbol.trim().toUpperCase()) return null;
  const price = tick.lastPrice ?? tick.price;
  return price != null && Number.isFinite(price) && price > 0 ? price : null;
}
