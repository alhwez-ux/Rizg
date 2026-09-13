import { NextResponse } from "next/server";

import { TASI_MARKET } from "@/lib/marketData";

export const dynamic = "force-dynamic";

type CloseQuote = {
  symbol: string;
  close: number;
  previous_close: number | null;
  change_percent: number;
  volume: number;
  value_traded: number;
  open: number | null;
  high: number | null;
  low: number | null;
  volume_ratio: number | null;
  as_of: string;
};

let cached: { at: number; body: { success: boolean; as_of: string | null; source: string; data: CloseQuote[] } } | null =
  null;
const CACHE_MS = 45_000;

function toFinite(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function arabicGregorian(iso: string): string {
  const [year, month, day] = iso.split("-").map((part) => Number(part));
  const months = [
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
  ];
  if (!year || !month || !day || month < 1 || month > 12) return iso;
  return `${day} ${months[month - 1]} ${year}`;
}

function riyadhDay(unix: number): string {
  return new Date(unix * 1000).toLocaleDateString("en-CA", { timeZone: "Asia/Riyadh" });
}

async function fetchSymbolClose(symbol: string): Promise<CloseQuote | null> {
  const response = await fetch(
    `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}.SR?interval=1d&range=1mo`,
    {
      cache: "no-store",
      headers: {
        "User-Agent": "Mozilla/5.0 RizgRadar",
        Accept: "application/json",
      },
    },
  );
  if (!response.ok) return null;
  const payload = (await response.json()) as {
    chart?: {
      result?: Array<{
        meta?: Record<string, unknown>;
        timestamp?: number[];
        indicators?: { quote?: Array<Record<string, unknown>> };
      }>;
    };
  };
  const result = payload.chart?.result?.[0];
  if (!result) return null;
  const timestamps = result.timestamp ?? [];
  const quote = result.indicators?.quote?.[0] ?? {};
  const closes = Array.isArray(quote.close) ? quote.close : [];
  const volumes = Array.isArray(quote.volume) ? quote.volume : [];
  const opens = Array.isArray(quote.open) ? quote.open : [];
  const highs = Array.isArray(quote.high) ? quote.high : [];
  const lows = Array.isArray(quote.low) ? quote.low : [];
  const bars: Array<{
    as_of: string;
    close: number;
    volume: number;
    open: number | null;
    high: number | null;
    low: number | null;
  }> = [];
  for (let index = 0; index < timestamps.length; index += 1) {
    const close = toFinite(closes[index]);
    if (close == null) continue;
    bars.push({
      as_of: riyadhDay(timestamps[index]),
      close,
      volume: toFinite(volumes[index]) ?? 0,
      open: toFinite(opens[index]),
      high: toFinite(highs[index]),
      low: toFinite(lows[index]),
    });
  }
  const last = bars.at(-1);
  const previous = bars.at(-2);
  const metaPrice = toFinite(result.meta?.regularMarketPrice);
  const metaPrev = toFinite(result.meta?.chartPreviousClose ?? result.meta?.previousClose);
  const metaVol = toFinite(result.meta?.regularMarketVolume);
  const close = last?.close ?? metaPrice;
  if (close == null) return null;
  const previousClose = previous?.close ?? metaPrev;
  const change =
    toFinite(result.meta?.regularMarketChangePercent) ??
    (previousClose ? ((close - previousClose) / previousClose) * 100 : 0);
  const asOf =
    last?.as_of ??
    (typeof result.meta?.regularMarketTime === "number"
      ? riyadhDay(result.meta.regularMarketTime)
      : riyadhDay(Date.now() / 1000));
  const high = last?.high ?? toFinite(result.meta?.regularMarketDayHigh);
  const low = last?.low ?? toFinite(result.meta?.regularMarketDayLow);
  const open = last?.open ?? toFinite(result.meta?.regularMarketOpen);
  const volume = Math.round(last?.volume || metaVol || 0);
  const typical = high != null && low != null ? (high + low + close) / 3 : close;
  const priorVolumes = bars.slice(0, -1).map((bar) => bar.volume).filter((item) => item > 0);
  const avgVolume =
    priorVolumes.length > 0 ? priorVolumes.slice(-20).reduce((sum, item) => sum + item, 0) / Math.min(priorVolumes.length, 20) : 0;
  return {
    symbol,
    close: Number(close.toFixed(4)),
    previous_close: previousClose != null ? Number(previousClose.toFixed(4)) : null,
    change_percent: Number(change.toFixed(2)),
    volume,
    value_traded: Math.round(typical * volume),
    open: open != null ? Number(open.toFixed(4)) : null,
    high: high != null ? Number(high.toFixed(4)) : null,
    low: low != null ? Number(low.toFixed(4)) : null,
    volume_ratio: avgVolume > 0 ? Number((volume / avgVolume).toFixed(2)) : null,
    as_of: asOf,
  };
}

export async function GET() {
  if (cached && Date.now() - cached.at < CACHE_MS) {
    return NextResponse.json(cached.body);
  }
  const quotes = (
    await Promise.all(
      TASI_MARKET.map(async (row) => {
        try {
          return await fetchSymbolClose(row.symbol);
        } catch {
          return null;
        }
      }),
    )
  ).filter((row): row is CloseQuote => row != null);

  const asOf = quotes.reduce<string | null>((latest, row) => {
    if (!latest || row.as_of > latest) return row.as_of;
    return latest;
  }, null);
  const label = asOf ? `تاسي — إغلاق ${arabicGregorian(asOf)}` : "تاسي — آخر إغلاق رسمي";
  const body = {
    success: quotes.length > 0,
    as_of: asOf,
    source: label,
    data: quotes,
  };
  if (quotes.length) cached = { at: Date.now(), body };
  return NextResponse.json(body, { status: quotes.length ? 200 : 502 });
}
