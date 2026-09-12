import { ComplianceStatus, type FinancialGrade, type Quarter } from "@prisma/client";

import { applyPurification, RADAR_ELIGIBLE_STATUSES } from "./purification";
import { pickNextDividend, serializeDividend, type CashDividend } from "./dividends";
import { prisma } from "@/lib/prisma";

export interface RadarComplianceStock {
  symbol: string;
  companyNameAr: string;
  companyNameEn: string;
  currentStatus: "PURE" | "MIXED";
  sector: string;
  updatedAt: Date;
  quarter: string | null;
  purificationRate: number;
  debtRatio: number | null;
  impureIncomeRatio: number | null;
  purificationApplied: boolean;
  purificationDue: number;
  purifiedNet: number;
  financialGrade: FinancialGrade;
  gradeScore: number;
  gradeSolvency: number;
  gradeDividends: number;
  gradeValuation: number;
  gradeGrowth: number;
  peRatio: number | null;
  pbRatio: number | null;
  dividendYield: number | null;
  revenueGrowth: number | null;
  operatingGrowth: number | null;
  netIncomeMargin: number | null;
  isLosing: boolean;
  lossReason: string | null;
  rsi: number | null;
  ema50: number | null;
  ema200: number | null;
  macd: number | null;
  avgVolume: number | null;
  nextDividend: CashDividend | null;
  dividends: CashDividend[];
}

function quarterLabel(year: number, quarter: Quarter): string {
  return `${year}-${quarter}`;
}

/**
 * Liquidity-radar universe: PURE and MIXED only.
 * PROHIBITED is excluded by Prisma `in` and again in memory.
 * MIXED names receive the latest quarterly purification rate.
 */
export async function getActiveStocksForRadar(): Promise<RadarComplianceStock[]> {
  const stocks = await prisma.stockCompliance.findMany({
    where: {
      currentStatus: { in: [...RADAR_ELIGIBLE_STATUSES] },
    },
    include: {
      history: {
        orderBy: [{ year: "desc" }, { quarter: "desc" }],
        take: 1,
      },
      dividends: {
        orderBy: { eligibilityDate: "desc" },
      },
    },
    orderBy: { symbol: "asc" },
  });

  return stocks.flatMap((stock) => {
    if (stock.currentStatus === ComplianceStatus.PROHIBITED) return [];

    const latest = stock.history[0] ?? null;
    const purification = applyPurification(
      1,
      stock.currentStatus,
      latest?.purificationRate ?? 0,
    );
    if (!purification) return [];

    const dividends = stock.dividends.map((item) =>
      serializeDividend({
        announcementDate: item.announcementDate,
        eligibilityDate: item.eligibilityDate,
        distributionDate: item.distributionDate,
        amountPerShare: item.amountPerShare,
      }),
    );

    return [
      {
        symbol: stock.symbol,
        companyNameAr: stock.companyNameAr,
        companyNameEn: stock.companyNameEn,
        currentStatus: stock.currentStatus,
        sector: stock.sector,
        updatedAt: stock.updatedAt,
        quarter: latest ? quarterLabel(latest.year, latest.quarter) : null,
        purificationRate: purification.rate,
        debtRatio: latest?.debtRatio ?? null,
        impureIncomeRatio: latest?.impureIncomeRatio ?? null,
        purificationApplied: purification.applied,
        purificationDue: purification.due,
        purifiedNet: purification.net,
        financialGrade: stock.financialGrade,
        gradeScore: stock.gradeScore,
        gradeSolvency: stock.gradeSolvency,
        gradeDividends: stock.gradeDividends,
        gradeValuation: stock.gradeValuation,
        gradeGrowth: stock.gradeGrowth,
        peRatio: stock.peRatio,
        pbRatio: stock.pbRatio,
        dividendYield: stock.dividendYield,
        revenueGrowth: stock.revenueGrowth,
        operatingGrowth: stock.operatingGrowth,
        netIncomeMargin: stock.netIncomeMargin,
        isLosing: stock.isLosing,
        lossReason: stock.lossReason,
        rsi: stock.rsi,
        ema50: stock.ema50,
        ema200: stock.ema200,
        macd: stock.macd,
        avgVolume: stock.avgVolume,
        nextDividend: pickNextDividend(dividends),
        dividends,
      },
    ];
  });
}

export async function getStockHistory(symbol: string) {
  const ticker = symbol.trim();
  if (!ticker) return [];

  const stock = await prisma.stockCompliance.findUnique({
    where: { symbol: ticker },
    include: {
      history: { orderBy: [{ year: "desc" }, { quarter: "desc" }] },
    },
  });

  return stock?.history ?? [];
}

export async function getProhibitedSymbols(): Promise<string[]> {
  const rows = await prisma.stockCompliance.findMany({
    where: { currentStatus: ComplianceStatus.PROHIBITED },
    select: { symbol: true },
    orderBy: { symbol: "asc" },
  });
  return rows.map((row) => row.symbol);
}

export const radarComplianceService = {
  getActiveStocksForRadar,
  getProhibitedSymbols,
  getStockHistory,
  applyPurification,
};
