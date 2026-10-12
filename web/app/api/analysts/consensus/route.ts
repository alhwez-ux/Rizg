import { NextRequest, NextResponse } from "next/server";

import { ANALYST_BOOK, buildAnalystConsensus, buildRollingConsensus, riyadhToday } from "@/lib/analystBook";
import { isProhibitedStock } from "@/lib/shariah";
import { fetchYahooLasts } from "@/lib/yahooLast";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const pureOnly = request.nextUrl.searchParams.get("pure_only") === "true";
  const windowRaw = Number(request.nextUrl.searchParams.get("window_days") || "");
  const windowDays = Number.isFinite(windowRaw) && windowRaw >= 1 && windowRaw <= 30 ? windowRaw : 0;
  const today = riyadhToday();
  const symbols = ANALYST_BOOK.filter((item) => {
    if (isProhibitedStock(item.symbol)) return false;
    if (windowDays) return Boolean(item.published_on);
    return item.valid_until >= today;
  }).map((item) => item.symbol);
  const lastPrices = await fetchYahooLasts(symbols);
  if (windowDays) {
    return NextResponse.json(buildRollingConsensus(pureOnly, today, lastPrices, windowDays));
  }
  return NextResponse.json(buildAnalystConsensus(pureOnly, today, lastPrices));
}
