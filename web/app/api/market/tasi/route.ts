import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETASI.SR?interval=1d&range=5d";

type TasiQuote = {
  index: "TASI";
  value: number | null;
  changePercent: number | null;
};

let cached: { at: number; quote: TasiQuote } | null = null;
const CACHE_MS = 30_000;

function toFinite(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export async function GET() {
  if (cached && Date.now() - cached.at < CACHE_MS) {
    return NextResponse.json(cached.quote);
  }

  try {
    const response = await fetch(YAHOO_CHART, {
      cache: "no-store",
      headers: {
        "User-Agent": "Mozilla/5.0 RizgRadar",
        Accept: "application/json",
      },
    });
    if (!response.ok) {
      throw new Error(`yahoo_${response.status}`);
    }
    const payload = (await response.json()) as {
      chart?: { result?: Array<{ meta?: Record<string, unknown> }> };
    };
    const meta = payload.chart?.result?.[0]?.meta ?? {};
    const value = toFinite(meta.regularMarketPrice);
    const previous = toFinite(meta.chartPreviousClose ?? meta.previousClose);
    const quotedChange = toFinite(meta.regularMarketChangePercent);
    const changePercent =
      quotedChange ??
      (value != null && previous != null && previous !== 0 ? ((value - previous) / previous) * 100 : null);

    const quote: TasiQuote = { index: "TASI", value, changePercent };
    cached = { at: Date.now(), quote };
    return NextResponse.json(quote);
  } catch {
    if (cached) return NextResponse.json(cached.quote);
    return NextResponse.json({ index: "TASI", value: null, changePercent: null }, { status: 502 });
  }
}
