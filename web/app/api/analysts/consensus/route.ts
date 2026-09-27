import { NextRequest, NextResponse } from "next/server";

import { ANALYST_BOOK, buildAnalystConsensus, riyadhToday } from "@/lib/analystBook";
import { isProhibitedStock } from "@/lib/shariah";
import { fetchYahooLasts } from "@/lib/yahooLast";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const pureOnly = request.nextUrl.searchParams.get("pure_only") === "true";
  const today = riyadhToday();
  const symbols = ANALYST_BOOK.filter((item) => item.valid_until >= today && !isProhibitedStock(item.symbol)).map(
    (item) => item.symbol,
  );
  const lastPrices = await fetchYahooLasts(symbols);
  return NextResponse.json(buildAnalystConsensus(pureOnly, today, lastPrices));
}
