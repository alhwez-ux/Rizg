import {
  collection,
  getDocs,
  orderBy,
  query,
  Timestamp,
  where,
  type DocumentData,
  type QueryDocumentSnapshot,
} from "firebase/firestore";

import { getDb, HISTORY_SUBCOLLECTION, STOCKS_COLLECTION } from "./client";
import {
  isProhibitedStatus,
  isRadarEligibleStatus,
  toRadarTableRow,
  type ComplianceHistory,
  type ComplianceStatus,
  type RadarTableRow,
  type Stock,
} from "./types";

function toDate(value: unknown): Date {
  if (value instanceof Timestamp) return value.toDate();
  if (value instanceof Date) return value;
  if (typeof value === "string" || typeof value === "number") {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }
  return new Date();
}

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function parseStatus(value: unknown): ComplianceStatus {
  if (value === "PURE" || value === "MIXED" || value === "PROHIBITED") {
    return value;
  }
  return "PROHIBITED";
}

function docToStock(snapshot: QueryDocumentSnapshot<DocumentData>): Stock {
  const data = snapshot.data();
  return {
    symbol: String(data.symbol ?? snapshot.id),
    companyNameAr: String(data.companyNameAr ?? ""),
    companyNameEn: String(data.companyNameEn ?? ""),
    currentStatus: parseStatus(data.currentStatus),
    sector: String(data.sector ?? ""),
    updatedAt: toDate(data.updatedAt),
  };
}

function docToHistory(snapshot: QueryDocumentSnapshot<DocumentData>): ComplianceHistory {
  const data = snapshot.data();
  return {
    quarter: String(data.quarter ?? snapshot.id),
    status: parseStatus(data.status),
    purificationRate: toNumber(data.purificationRate),
    debtRatio: toNumber(data.debtRatio),
    impureIncomeRatio: toNumber(data.impureIncomeRatio),
  };
}

/**
 * Fetch PURE and MIXED stocks for the liquidity radar.
 * Uses Firestore `where(..., "in", ["PURE", "MIXED"])` so PROHIBITED documents
 * are never returned by the query, then drops any prohibited row in memory.
 */
export async function getActiveStocksForRadar(): Promise<Stock[]> {
  const stocksRef = collection(getDb(), STOCKS_COLLECTION);
  const radarQuery = query(stocksRef, where("currentStatus", "in", ["PURE", "MIXED"]));
  const snapshot = await getDocs(radarQuery);

  return snapshot.docs
    .map(docToStock)
    .filter((stock) => isRadarEligibleStatus(stock.currentStatus) && !isProhibitedStatus(stock.currentStatus))
    .sort((a, b) => a.symbol.localeCompare(b.symbol, "en"));
}

/**
 * Fetch purification / compliance history for one symbol from stocks/{symbol}/history.
 */
export async function getStockHistory(symbol: string): Promise<ComplianceHistory[]> {
  const ticker = symbol.trim();
  if (!ticker) return [];

  const historyRef = collection(getDb(), STOCKS_COLLECTION, ticker, HISTORY_SUBCOLLECTION);
  const historyQuery = query(historyRef, orderBy("quarter", "desc"));
  const snapshot = await getDocs(historyQuery);

  return snapshot.docs.map(docToHistory);
}

/** Eligible radar names with the latest history row (purification / debt / impure income). */
export async function getRadarTableRows(): Promise<RadarTableRow[]> {
  const stocks = await getActiveStocksForRadar();
  const rows = await Promise.all(
    stocks.map(async (stock) => {
      const history = await getStockHistory(stock.symbol);
      return toRadarTableRow(stock, history[0] ?? null);
    }),
  );
  return rows.filter((row): row is RadarTableRow => row != null);
}

export const stockService = {
  getActiveStocksForRadar,
  getStockHistory,
  getRadarTableRows,
};
