import { apiFetch } from "@/lib/api";
import { readLiveCache, writeLiveCache } from "@/lib/liveCache";
import { toFiniteNumber } from "@/lib/screener";

const CACHE_KEY = "ranking-matrix";

export interface RankingRow {
  rank: number;
  symbol: string;
  name: string;
  profit_growth: number | null;
  dividend_yield: number | null;
  roe: number | null;
  roa: number | null;
  pe_ratio: number | null;
  net_income: number | null;
  matrix_score: number;
  category: string;
}

export interface RankingMatrixResponse {
  success: boolean;
  total_companies: number;
  source?: string;
  message?: string;
  data: RankingRow[];
}

export async function fetchRankingMatrix(): Promise<RankingMatrixResponse> {
  const cached = readLiveCache<RankingMatrixResponse>(CACHE_KEY);
  try {
    const response = await apiFetch("/api/v1/market/ranking-matrix", {
      method: "GET",
    });
    const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
    if (!response.ok) {
      return cached ?? emptyRanking();
    }
    const rows = Array.isArray(payload?.data) ? payload.data : [];
    const data = rows.map((row, index) => parseRow(row, index));
    const result: RankingMatrixResponse = {
      success: true,
      total_companies: Number(payload?.total_companies) || data.length,
      source: String(payload?.source ?? "Sahm API"),
      message: payload?.message ? String(payload.message) : undefined,
      data,
    };
    if (data.length) {
      writeLiveCache(CACHE_KEY, result);
      return result;
    }
    if (cached?.data?.length) {
      return { ...cached, source: "cached" };
    }
    return result;
  } catch {
    return cached ?? emptyRanking();
  }
}

function emptyRanking(): RankingMatrixResponse {
  return { success: true, total_companies: 0, source: "Sahm API", data: [] };
}

function missingAsNull(value: number | null): number | null {
  if (value == null || value === 0) return null;
  return value;
}

function parseRow(raw: unknown, index: number): RankingRow {
  const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    rank: toFiniteNumber(row.rank) ?? index + 1,
    symbol: String(row.symbol ?? ""),
    name: String(row.name ?? row.symbol ?? ""),
    profit_growth: toFiniteNumber(row.profit_growth),
    dividend_yield: toFiniteNumber(row.dividend_yield),
    roe: toFiniteNumber(row.roe),
    roa: toFiniteNumber(row.roa),
    pe_ratio: missingAsNull(toFiniteNumber(row.pe_ratio)),
    net_income: toFiniteNumber(row.net_income),
    matrix_score: toFiniteNumber(row.matrix_score) ?? 0,
    category: String(row.category ?? ""),
  };
}
