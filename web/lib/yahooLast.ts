export async function fetchYahooLast(symbol: string): Promise<number | null> {
  const ticker = symbol.trim().toUpperCase();
  if (!/^\d{4}$/.test(ticker)) return null;
  const response = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${ticker}.SR?interval=1m&range=1d`, {
    cache: "no-store",
    headers: {
      "User-Agent": "Mozilla/5.0 RizgRadar",
      Accept: "application/json",
    },
  });
  if (!response.ok) return null;
  const payload = (await response.json()) as {
    chart?: {
      result?: Array<{
        meta?: { regularMarketPrice?: number };
        indicators?: { quote?: Array<{ close?: Array<number | null> }> };
      }>;
    };
  };
  const result = payload.chart?.result?.[0];
  const live = result?.meta?.regularMarketPrice;
  if (typeof live === "number" && Number.isFinite(live) && live > 0) return live;
  const closes = result?.indicators?.quote?.[0]?.close ?? [];
  for (let index = closes.length - 1; index >= 0; index -= 1) {
    const close = closes[index];
    if (typeof close === "number" && Number.isFinite(close) && close > 0) return close;
  }
  return null;
}

export async function fetchYahooLasts(symbols: string[]): Promise<Record<string, number>> {
  const unique = [...new Set(symbols.map((symbol) => symbol.trim().toUpperCase()).filter((symbol) => /^\d{4}$/.test(symbol)))];
  const pairs = await Promise.all(
    unique.map(async (symbol) => {
      try {
        const price = await fetchYahooLast(symbol);
        return [symbol, price] as const;
      } catch {
        return [symbol, null] as const;
      }
    }),
  );
  const prices: Record<string, number> = {};
  for (const [symbol, price] of pairs) {
    if (price != null) prices[symbol] = price;
  }
  return prices;
}
