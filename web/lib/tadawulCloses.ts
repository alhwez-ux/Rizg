import { MARKET_AS_OF, MARKET_SOURCE, TASI_MARKET, type TasiCompany } from "@/lib/marketData";

export interface TadawulCloseQuote {
  symbol: string;
  close: number;
  previous_close: number | null;
  change_percent: number;
  volume: number;
  value_traded?: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume_ratio?: number | null;
  as_of: string;
}

export interface TadawulClosesResponse {
  success: boolean;
  as_of: string | null;
  source: string;
  data: TadawulCloseQuote[];
}

export interface TasiTapeSnapshot {
  rows: TasiCompany[];
  source: string;
  asOf: string;
}

export function overlayTadawulCloses(base: TasiCompany[], quotes: TadawulCloseQuote[]): TasiCompany[] {
  if (!quotes.length) return base.map((row) => ({ ...row }));
  const bySymbol = new Map(quotes.map((quote) => [quote.symbol, quote]));
  return base.map((row) => {
    const quote = bySymbol.get(row.symbol);
    if (!quote) return { ...row };
    return {
      ...row,
      close: quote.close,
      change_percent: quote.change_percent,
      volume: quote.volume || row.volume,
      value_traded: quote.value_traded && quote.value_traded > 0 ? quote.value_traded : row.value_traded,
      open: quote.open ?? row.open,
      high: quote.high ?? row.high,
      low: quote.low ?? row.low,
      volume_ratio: quote.volume_ratio ?? row.volume_ratio,
    };
  });
}

export async function loadTasiTape(): Promise<TasiTapeSnapshot> {
  try {
    const response = await fetch("/api/market/closes", { cache: "no-store" });
    if (!response.ok) {
      return { rows: TASI_MARKET, source: MARKET_SOURCE, asOf: MARKET_AS_OF };
    }
    const payload = (await response.json()) as TadawulClosesResponse;
    const quotes = Array.isArray(payload.data) ? payload.data : [];
    if (!quotes.length) {
      return { rows: TASI_MARKET, source: MARKET_SOURCE, asOf: MARKET_AS_OF };
    }
    return {
      rows: overlayTadawulCloses(TASI_MARKET, quotes),
      source: payload.source || MARKET_SOURCE,
      asOf: payload.as_of || MARKET_AS_OF,
    };
  } catch {
    return { rows: TASI_MARKET, source: MARKET_SOURCE, asOf: MARKET_AS_OF };
  }
}
