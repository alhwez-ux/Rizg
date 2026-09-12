import { classifyLoss, gradeCompany, type FinancialGrade } from "./grading";
import { serializeDividend, type CashDividend } from "./dividends";
import type { UniverseStock } from "../../prisma/tasiUniverse";

export interface DerivedFundamentals {
  peRatio: number;
  pbRatio: number;
  dividendYield: number;
  revenueGrowth: number;
  operatingGrowth: number;
  netIncomeMargin: number;
  currentRatio: number;
  dividendYears: number;
  rsi: number;
  ema50: number;
  ema200: number;
  macd: number;
  avgVolume: number;
  financialGrade: FinancialGrade;
  gradeScore: number;
  gradeSolvency: number;
  gradeDividends: number;
  gradeValuation: number;
  gradeGrowth: number;
  isLosing: boolean;
  lossReason: string | null;
  dividends: CashDividend[];
}

function unit(symbol: string, salt: number): number {
  const n = Number(symbol.replace(/\D/g, "")) || 1;
  return ((n * 17 + salt * 13) % 1000) / 1000;
}

function addDays(base: Date, days: number): Date {
  const next = new Date(base);
  next.setDate(next.getDate() + days);
  return next;
}

/**
 * Deterministic illustrative fundamentals for a TASI name.
 * Not official financials — used so every eligible company gets the same rule set.
 */
export function deriveFundamentals(stock: UniverseStock, asOf = new Date()): DerivedFundamentals {
  const u1 = unit(stock.symbol, 1);
  const u2 = unit(stock.symbol, 2);
  const u3 = unit(stock.symbol, 3);
  const u4 = unit(stock.symbol, 4);
  const islamic = stock.currentStatus === "PURE";

  const peRatio = islamic ? 12 + u1 * 8 : 8 + u1 * 24;
  const pbRatio = islamic ? 1.1 + u2 * 1.6 : 0.7 + u2 * 3.4;
  const paysDividend = stock.currentStatus !== "PROHIBITED" && u3 > 0.28;
  const dividendYield = paysDividend ? (islamic ? 0.028 + u4 * 0.025 : 0.012 + u4 * 0.05) : 0;
  const revenueGrowth = islamic ? 0.04 + u1 * 0.14 : -0.1 + u2 * 0.32;
  const operatingGrowth = islamic ? 0.03 + u3 * 0.12 : -0.14 + u1 * 0.34;
  const netIncomeMargin = islamic ? 0.18 + u4 * 0.12 : -0.09 + u3 * 0.28;
  const currentRatio = islamic ? 1.4 + u1 * 0.8 : 0.7 + u2 * 2.1;
  const dividendYears = paysDividend ? 2 + Math.floor(u2 * 7) : Math.floor(u1 * 2);

  const ema200 = 18 + u3 * 48;
  const ema50 = ema200 * (0.9 + u1 * 0.22);
  const rsi = 22 + u4 * 58;
  const macd = (ema50 - ema200) * 0.12;
  const avgVolume = 400_000 + u2 * 4_800_000;

  const amountPerShare = paysDividend ? Number((0.25 + u3 * 2.4).toFixed(2)) : 0;
  const dividends: CashDividend[] = [];
  if (paysDividend) {
    const eligibility = addDays(asOf, Math.floor(u1 * 40) - 4);
    dividends.push(
      serializeDividend({
        announcementDate: addDays(eligibility, -18),
        eligibilityDate: eligibility,
        distributionDate: addDays(eligibility, 16 + Math.floor(u4 * 20)),
        amountPerShare,
      }),
    );
    dividends.push(
      serializeDividend({
        announcementDate: addDays(eligibility, -200),
        eligibilityDate: addDays(eligibility, -182),
        distributionDate: addDays(eligibility, -160),
        amountPerShare: Number((amountPerShare * 0.92).toFixed(2)),
      }),
    );
  }

  const graded = gradeCompany({
    debtRatio: stock.debtRatio,
    currentRatio,
    dividendYield,
    consecutiveYears: dividendYears,
    amountPerShare,
    peRatio,
    pbRatio,
    revenueGrowth,
    operatingGrowth,
  });
  const loss = classifyLoss({ netIncomeMargin, operatingGrowth, ema50, ema200, rsi });

  return {
    peRatio: Number(peRatio.toFixed(2)),
    pbRatio: Number(pbRatio.toFixed(2)),
    dividendYield: Number(dividendYield.toFixed(4)),
    revenueGrowth: Number(revenueGrowth.toFixed(4)),
    operatingGrowth: Number(operatingGrowth.toFixed(4)),
    netIncomeMargin: Number(netIncomeMargin.toFixed(4)),
    currentRatio: Number(currentRatio.toFixed(2)),
    dividendYears,
    rsi: Number(rsi.toFixed(1)),
    ema50: Number(ema50.toFixed(2)),
    ema200: Number(ema200.toFixed(2)),
    macd: Number(macd.toFixed(3)),
    avgVolume: Math.round(avgVolume),
    financialGrade: graded.grade,
    gradeScore: Number(graded.total.toFixed(1)),
    gradeSolvency: Number(graded.solvency.toFixed(1)),
    gradeDividends: Number(graded.dividends.toFixed(1)),
    gradeValuation: Number(graded.valuation.toFixed(1)),
    gradeGrowth: Number(graded.growth.toFixed(1)),
    isLosing: loss.isLosing,
    lossReason: loss.lossReason,
    dividends,
  };
}
