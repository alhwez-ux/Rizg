import { serverTimestamp, writeBatch } from "firebase/firestore";

import { getDb, historyDocRef, stockDocRef } from "./client";
import { toRadarTableRow } from "./types";
import type { ComplianceHistory, RadarTableRow, Stock } from "./types";

export function currentQuarter(date = new Date()): string {
  const quarter = Math.floor(date.getMonth() / 3) + 1;
  return `${date.getFullYear()}-Q${quarter}`;
}

function previousQuarter(quarter: string): string {
  const match = /^(\d{4})-Q([1-4])$/.exec(quarter);
  if (!match) return quarter;
  const year = Number(match[1]);
  const q = Number(match[2]);
  if (q === 1) return `${year - 1}-Q4`;
  return `${year}-Q${q - 1}`;
}

type SeedStock = Omit<Stock, "updatedAt"> & {
  history: ComplianceHistory[];
};

function sampleUniverse(asOf = new Date()): SeedStock[] {
  const q0 = currentQuarter(asOf);
  const q1 = previousQuarter(q0);
  const q2 = previousQuarter(q1);

  return [
    {
      symbol: "2222",
      companyNameAr: "أرامكو السعودية",
      companyNameEn: "Saudi Aramco",
      currentStatus: "MIXED",
      sector: "الطاقة",
      history: [
        { quarter: q0, status: "MIXED", purificationRate: 0.0018, debtRatio: 0.19, impureIncomeRatio: 0.021 },
        { quarter: q1, status: "MIXED", purificationRate: 0.0021, debtRatio: 0.2, impureIncomeRatio: 0.024 },
        { quarter: q2, status: "MIXED", purificationRate: 0.0016, debtRatio: 0.18, impureIncomeRatio: 0.019 },
      ],
    },
    {
      symbol: "1120",
      companyNameAr: "مصرف الراجحي",
      companyNameEn: "Al Rajhi Bank",
      currentStatus: "PURE",
      sector: "المصارف",
      history: [
        { quarter: q0, status: "PURE", purificationRate: 0, debtRatio: 0.04, impureIncomeRatio: 0 },
        { quarter: q1, status: "PURE", purificationRate: 0, debtRatio: 0.05, impureIncomeRatio: 0 },
        { quarter: q2, status: "PURE", purificationRate: 0, debtRatio: 0.05, impureIncomeRatio: 0 },
      ],
    },
    {
      symbol: "4300",
      companyNameAr: "دار الأركان",
      companyNameEn: "Dar Al Arkan",
      currentStatus: "MIXED",
      sector: "العقارات",
      history: [
        { quarter: q0, status: "MIXED", purificationRate: 0.028, debtRatio: 0.36, impureIncomeRatio: 0.041 },
        { quarter: q1, status: "MIXED", purificationRate: 0.031, debtRatio: 0.38, impureIncomeRatio: 0.044 },
        { quarter: q2, status: "MIXED", purificationRate: 0.026, debtRatio: 0.34, impureIncomeRatio: 0.039 },
      ],
    },
    {
      symbol: "1050",
      companyNameAr: "البنك السعودي البريطاني",
      companyNameEn: "SABB",
      currentStatus: "PROHIBITED",
      sector: "المصارف",
      history: [
        { quarter: q0, status: "PROHIBITED", purificationRate: 1, debtRatio: 0.62, impureIncomeRatio: 0.71 },
        { quarter: q1, status: "PROHIBITED", purificationRate: 1, debtRatio: 0.61, impureIncomeRatio: 0.69 },
        { quarter: q2, status: "PROHIBITED", purificationRate: 1, debtRatio: 0.6, impureIncomeRatio: 0.68 },
      ],
    },
  ];
}

export interface SeedRadarResult {
  quarter: string;
  stocksWritten: number;
  historyWritten: number;
  eligibleSymbols: string[];
  excludedSymbols: string[];
}

/**
 * Demo seed for the liquidity radar. Statuses are illustrative fixtures, not a fatwa.
 * Includes one PROHIBITED name so getActiveStocksForRadar() can be verified to drop it.
 */
export async function seedRadarStocks(asOf = new Date()): Promise<SeedRadarResult> {
  const db = getDb();
  const batch = writeBatch(db);
  const universe = sampleUniverse(asOf);
  const quarter = currentQuarter(asOf);
  let historyWritten = 0;

  for (const stock of universe) {
    batch.set(stockDocRef(stock.symbol), {
      symbol: stock.symbol,
      companyNameAr: stock.companyNameAr,
      companyNameEn: stock.companyNameEn,
      currentStatus: stock.currentStatus,
      sector: stock.sector,
      updatedAt: serverTimestamp(),
    });

    for (const row of stock.history) {
      batch.set(historyDocRef(stock.symbol, row.quarter), row);
      historyWritten += 1;
    }
  }

  await batch.commit();

  const eligibleSymbols = universe
    .filter((stock) => stock.currentStatus !== "PROHIBITED")
    .map((stock) => stock.symbol);
  const excludedSymbols = universe
    .filter((stock) => stock.currentStatus === "PROHIBITED")
    .map((stock) => stock.symbol);

  return {
    quarter,
    stocksWritten: universe.length,
    historyWritten,
    eligibleSymbols,
    excludedSymbols,
  };
}

/** Local demo rows for the radar table when Firestore is not configured. */
export function getSampleRadarTableRows(asOf = new Date()): RadarTableRow[] {
  return sampleUniverse(asOf)
    .map((stock) =>
      toRadarTableRow(
        {
          symbol: stock.symbol,
          companyNameAr: stock.companyNameAr,
          companyNameEn: stock.companyNameEn,
          currentStatus: stock.currentStatus,
          sector: stock.sector,
          updatedAt: asOf,
        },
        stock.history[0] ?? null,
      ),
    )
    .filter((row): row is RadarTableRow => row != null);
}
