"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ar } from "@/lib/ar";
import {
  isProhibitedStatus,
  isRadarEligibleStatus,
  type CashDividend,
  type RadarTableRow,
  type Stock,
} from "@/lib/firebase/types";

export interface UseStockRadarResult {
  rows: RadarTableRow[];
  stocks: Stock[];
  eligibleSymbols: Set<string>;
  prohibitedSymbols: Set<string>;
  loading: boolean;
  error: string | null;
  configured: boolean;
  refresh: () => Promise<void>;
}

function parseDividend(value: unknown): CashDividend | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const amount = Number(raw.amountPerShare);
  if (!Number.isFinite(amount)) return null;
  return {
    announcementDate: String(raw.announcementDate ?? ""),
    eligibilityDate: String(raw.eligibilityDate ?? ""),
    distributionDate: String(raw.distributionDate ?? ""),
    amountPerShare: amount,
  };
}

function parseRadarRows(payload: unknown): RadarTableRow[] {
  if (!payload || typeof payload !== "object") return [];
  const stocks = (payload as { stocks?: unknown }).stocks;
  if (!Array.isArray(stocks)) return [];

  return stocks.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const raw = item as Record<string, unknown>;
    const currentStatus = raw.currentStatus;
    if (currentStatus !== "PURE" && currentStatus !== "MIXED") return [];
    if (isProhibitedStatus(currentStatus) || !isRadarEligibleStatus(currentStatus)) return [];

    const grade =
      raw.financialGrade === "A" ||
      raw.financialGrade === "B" ||
      raw.financialGrade === "C" ||
      raw.financialGrade === "D" ||
      raw.financialGrade === "E"
        ? raw.financialGrade
        : "C";
    const row: RadarTableRow = {
      symbol: String(raw.symbol ?? ""),
      companyNameAr: String(raw.companyNameAr ?? ""),
      companyNameEn: String(raw.companyNameEn ?? ""),
      currentStatus,
      sector: String(raw.sector ?? ""),
      updatedAt: raw.updatedAt ? new Date(String(raw.updatedAt)) : new Date(),
      quarter: raw.quarter == null ? null : String(raw.quarter),
      purificationRate: typeof raw.purificationRate === "number" ? raw.purificationRate : null,
      debtRatio: typeof raw.debtRatio === "number" ? raw.debtRatio : null,
      impureIncomeRatio: typeof raw.impureIncomeRatio === "number" ? raw.impureIncomeRatio : null,
      financialGrade: grade,
      gradeScore: typeof raw.gradeScore === "number" ? raw.gradeScore : 50,
      gradeSolvency: typeof raw.gradeSolvency === "number" ? raw.gradeSolvency : 50,
      gradeDividends: typeof raw.gradeDividends === "number" ? raw.gradeDividends : 50,
      gradeValuation: typeof raw.gradeValuation === "number" ? raw.gradeValuation : 50,
      gradeGrowth: typeof raw.gradeGrowth === "number" ? raw.gradeGrowth : 50,
      peRatio: typeof raw.peRatio === "number" ? raw.peRatio : null,
      pbRatio: typeof raw.pbRatio === "number" ? raw.pbRatio : null,
      dividendYield: typeof raw.dividendYield === "number" ? raw.dividendYield : null,
      revenueGrowth: typeof raw.revenueGrowth === "number" ? raw.revenueGrowth : null,
      operatingGrowth: typeof raw.operatingGrowth === "number" ? raw.operatingGrowth : null,
      netIncomeMargin: typeof raw.netIncomeMargin === "number" ? raw.netIncomeMargin : null,
      isLosing: Boolean(raw.isLosing),
      lossReason: raw.lossReason == null ? null : String(raw.lossReason),
      rsi: typeof raw.rsi === "number" ? raw.rsi : null,
      ema50: typeof raw.ema50 === "number" ? raw.ema50 : null,
      ema200: typeof raw.ema200 === "number" ? raw.ema200 : null,
      macd: typeof raw.macd === "number" ? raw.macd : null,
      avgVolume: typeof raw.avgVolume === "number" ? raw.avgVolume : null,
      nextDividend: parseDividend(raw.nextDividend),
      dividends: Array.isArray(raw.dividends)
        ? raw.dividends.flatMap((item) => {
            const parsed = parseDividend(item);
            return parsed ? [parsed] : [];
          })
        : [],
    };
    return row.symbol ? [row] : [];
  });
}

/**
 * Fetch PURE and MIXED stocks for the liquidity radar.
 * PROHIBITED names are excluded by the Prisma service and again here.
 */
export function useStockRadar(): UseStockRadarResult {
  const [rows, setRows] = useState<RadarTableRow[]>([]);
  const [prohibitedSymbols, setProhibitedSymbols] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    setLoading(true);

    try {
      const response = await fetch("/api/radar/stocks", { cache: "no-store" });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const message =
          payload && typeof payload === "object" && "message" in payload
            ? String((payload as { message?: unknown }).message ?? ar.radarLoadError)
            : ar.radarLoadError;
        throw new Error(message);
      }
      if (!alive.current) return;
      setRows(parseRadarRows(payload));
      const prohibited =
        payload && typeof payload === "object" && Array.isArray((payload as { prohibitedSymbols?: unknown }).prohibitedSymbols)
          ? (payload as { prohibitedSymbols: unknown[] }).prohibitedSymbols.map(String)
          : [];
      setProhibitedSymbols(new Set(prohibited));
      setError(null);
    } catch (err) {
      if (!alive.current) return;
      setRows([]);
      setError(err instanceof Error && err.message ? err.message : ar.radarLoadError);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void refresh();
    return () => {
      alive.current = false;
    };
  }, [refresh]);

  const stocks = useMemo<Stock[]>(
    () =>
      rows.map((row) => ({
        symbol: row.symbol,
        companyNameAr: row.companyNameAr,
        companyNameEn: row.companyNameEn,
        currentStatus: row.currentStatus,
        sector: row.sector,
        updatedAt: row.updatedAt,
      })),
    [rows],
  );

  const eligibleSymbols = useMemo(() => new Set(rows.map((row) => row.symbol)), [rows]);
  const configured = error == null && !loading;

  return { rows, stocks, eligibleSymbols, prohibitedSymbols, loading, error, configured, refresh };
}
