import { getActiveStocksForRadar, getProhibitedSymbols } from "./radarService";
import { scanMarketOpportunities } from "./technicalScreener";
import type { RadarTableRow } from "@/lib/firebase/types";

export async function listRadarStocks() {
  const [stocks, prohibitedSymbols] = await Promise.all([
    getActiveStocksForRadar(),
    getProhibitedSymbols(),
  ]);

  return {
    stocks: stocks.map((stock) => ({
      ...stock,
      updatedAt: stock.updatedAt.toISOString(),
    })),
    opportunities: scanMarketOpportunities(stocks as unknown as RadarTableRow[]),
    prohibitedSymbols,
    count: stocks.length,
  };
}
