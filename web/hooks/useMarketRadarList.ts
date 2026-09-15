"use client";

import { useCallback, useEffect, useState } from "react";

import { listedNameFor } from "@/lib/listedCompanies";

export interface RadarCompany {
  symbol: string;
  symbolName: string;
}

export const DEFAULT_MARKET_RADAR: RadarCompany[] = [
  { symbol: "1120", symbolName: "الراجحي" },
  { symbol: "2222", symbolName: "أرامكو السعودية" },
  { symbol: "2010", symbolName: "سابك" },
  { symbol: "7010", symbolName: "اس تي سي" },
  { symbol: "1150", symbolName: "الإنماء" },
];

const STORAGE_KEY = "rizg-market-radar";

function normalizeCompany(value: unknown): RadarCompany | null {
  if (!value || typeof value !== "object") return null;
  const row = value as { symbol?: unknown; symbolName?: unknown; name?: unknown };
  const symbol = String(row.symbol ?? "")
    .trim()
    .toUpperCase();
  if (!/^\d{4}$/.test(symbol)) return null;
  const listed = listedNameFor(symbol);
  const rawName = String(row.symbolName ?? row.name ?? "").trim();
  const symbolName =
    listed || (rawName && rawName !== symbol && !/^\d{4}$/.test(rawName) ? rawName : symbol);
  return { symbol, symbolName: listed || symbolName };
}

function parseList(raw: string | null): RadarCompany[] | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return null;
    const companies: RadarCompany[] = [];
    const seen = new Set<string>();
    for (const item of parsed) {
      const company = normalizeCompany(item);
      if (!company || seen.has(company.symbol)) continue;
      seen.add(company.symbol);
      companies.push(company);
    }
    return companies;
  } catch {
    return null;
  }
}

export function useMarketRadarList() {
  const [companies, setCompanies] = useState<RadarCompany[]>(DEFAULT_MARKET_RADAR);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setCompanies(parseList(window.localStorage.getItem(STORAGE_KEY)) ?? DEFAULT_MARKET_RADAR);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(companies));
    } catch {
      /* quota / private mode */
    }
  }, [companies, ready]);

  const addCompany = useCallback((company: { symbol: string; name?: string; symbolName?: string }) => {
    const next = normalizeCompany({
      symbol: company.symbol,
      symbolName: company.symbolName ?? company.name,
    });
    if (!next) return;
    setCompanies((current) => {
      const rest = current.filter((item) => item.symbol !== next.symbol);
      if (current[0]?.symbol === next.symbol && current[0]?.symbolName === next.symbolName) {
        return current;
      }
      return [next, ...rest];
    });
  }, []);

  const removeCompany = useCallback((symbol: string) => {
    const ticker = symbol.trim().toUpperCase();
    setCompanies((current) => current.filter((item) => item.symbol !== ticker));
  }, []);

  return { companies, addCompany, removeCompany, ready };
}
