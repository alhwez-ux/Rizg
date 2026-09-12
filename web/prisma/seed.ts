import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { ComplianceStatus, FinancialGrade, Quarter, type Prisma } from "@prisma/client";

import { deriveFundamentals } from "../lib/compliance/fundamentals";
import { prisma } from "../lib/prisma";
import { TASI_COMPLIANCE_UNIVERSE } from "./tasiUniverse";

const YEAR = 2026;

function historyFor(stock: (typeof TASI_COMPLIANCE_UNIVERSE)[number]): Prisma.ComplianceHistoryCreateWithoutStockInput[] {
  const points = [
    { year: YEAR, quarter: Quarter.Q3, bump: 0 },
    { year: YEAR, quarter: Quarter.Q2, bump: 0.001 },
    { year: YEAR, quarter: Quarter.Q1, bump: -0.0005 },
    { year: YEAR - 1, quarter: Quarter.Q4, bump: 0.0003 },
  ];

  return points.map((point) => {
    if (stock.currentStatus === ComplianceStatus.PURE) {
      return {
        year: point.year,
        quarter: point.quarter,
        status: ComplianceStatus.PURE,
        purificationRate: 0,
        debtRatio: stock.debtRatio,
        impureIncomeRatio: 0,
      };
    }
    if (stock.currentStatus === ComplianceStatus.PROHIBITED) {
      return {
        year: point.year,
        quarter: point.quarter,
        status: ComplianceStatus.PROHIBITED,
        purificationRate: 1,
        debtRatio: stock.debtRatio,
        impureIncomeRatio: stock.impureIncomeRatio,
      };
    }
    const rate = Math.max(0, stock.purificationRate + point.bump);
    return {
      year: point.year,
      quarter: point.quarter,
      status: ComplianceStatus.MIXED,
      purificationRate: rate,
      debtRatio: stock.debtRatio,
      impureIncomeRatio: stock.impureIncomeRatio,
    };
  });
}

function toGrade(value: string): FinancialGrade {
  if (value === "A" || value === "B" || value === "C" || value === "D" || value === "E") return value;
  return FinancialGrade.C;
}

async function seed() {
  const jsonTargets = [
    path.join(process.cwd(), "prisma", "tasi-universe.json"),
    path.join(process.cwd(), "..", "data", "tasi_compliance.json"),
  ];
  for (const target of jsonTargets) {
    try {
      mkdirSync(path.dirname(target), { recursive: true });
      writeFileSync(target, `${JSON.stringify(TASI_COMPLIANCE_UNIVERSE, null, 2)}\n`, "utf8");
    } catch {
      /* Vercel / read-only paths */
    }
  }

  for (const stock of TASI_COMPLIANCE_UNIVERSE) {
    const historyCreate = historyFor(stock);
    const fundamentals = deriveFundamentals(stock);
    const dividendCreate = fundamentals.dividends.map((item) => ({
      announcementDate: new Date(item.announcementDate),
      eligibilityDate: new Date(item.eligibilityDate),
      distributionDate: new Date(item.distributionDate),
      amountPerShare: item.amountPerShare,
    }));
    const financial = {
      currentStatus: stock.currentStatus,
      sector: stock.sector,
      companyNameAr: stock.companyNameAr,
      companyNameEn: stock.companyNameEn,
      financialGrade: toGrade(fundamentals.financialGrade),
      gradeScore: fundamentals.gradeScore,
      gradeSolvency: fundamentals.gradeSolvency,
      gradeDividends: fundamentals.gradeDividends,
      gradeValuation: fundamentals.gradeValuation,
      gradeGrowth: fundamentals.gradeGrowth,
      peRatio: fundamentals.peRatio,
      pbRatio: fundamentals.pbRatio,
      dividendYield: fundamentals.dividendYield,
      revenueGrowth: fundamentals.revenueGrowth,
      operatingGrowth: fundamentals.operatingGrowth,
      netIncomeMargin: fundamentals.netIncomeMargin,
      currentRatio: fundamentals.currentRatio,
      dividendYears: fundamentals.dividendYears,
      rsi: fundamentals.rsi,
      ema50: fundamentals.ema50,
      ema200: fundamentals.ema200,
      macd: fundamentals.macd,
      avgVolume: fundamentals.avgVolume,
      isLosing: fundamentals.isLosing,
      lossReason: fundamentals.lossReason,
    };

    await prisma.stockCompliance.upsert({
      where: { symbol: stock.symbol },
      update: {
        ...financial,
        history: {
          deleteMany: {},
          create: historyCreate,
        },
        dividends: {
          deleteMany: {},
          create: dividendCreate,
        },
      },
      create: {
        symbol: stock.symbol,
        ...financial,
        history: { create: historyCreate },
        dividends: { create: dividendCreate },
      },
    });
  }

  const eligible = await prisma.stockCompliance.count({
    where: { currentStatus: { in: [ComplianceStatus.PURE, ComplianceStatus.MIXED] } },
  });
  const prohibited = await prisma.stockCompliance.count({
    where: { currentStatus: ComplianceStatus.PROHIBITED },
  });
  const losing = await prisma.stockCompliance.count({
    where: {
      isLosing: true,
      currentStatus: { in: [ComplianceStatus.PURE, ComplianceStatus.MIXED] },
    },
  });

  console.log("Seeded TASI compliance universe (illustrative, not a fatwa).");
  console.log(`Radar-eligible PURE+MIXED: ${eligible}`);
  console.log(`Excluded PROHIBITED: ${prohibited}`);
  console.log(`Losing names on radar: ${losing}`);
}

seed()
  .catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
