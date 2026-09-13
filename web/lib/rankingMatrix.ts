import { apiFetch } from "@/lib/api";

export interface RankingRow {
  rank: number;
  symbol: string;
  name: string;
  profit_growth: number;
  dividend_yield: number;
  roe: number;
  roa: number | null;
  pe_ratio: number;
  net_income: number;
  matrix_score: number;
  category: string;
}

export interface RankingMatrixResponse {
  success: boolean;
  total_companies: number;
  data: RankingRow[];
}

export async function fetchRankingMatrix(): Promise<RankingMatrixResponse> {
  const response = await apiFetch("/api/v1/market/ranking-matrix", {
    method: "GET",
  });
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : null;
    throw new Error(detail || "تعذر جلب مصفوفة ترتيب الشركات");
  }
  const rows = Array.isArray(payload?.data) ? payload.data : [];
  return {
    success: Boolean(payload?.success ?? true),
    total_companies: Number(payload?.total_companies) || rows.length,
    data: rows.map((row, index) => parseRow(row, index)),
  };
}

function parseRow(raw: unknown, index: number): RankingRow {
  const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    rank: Number(row.rank) || index + 1,
    symbol: String(row.symbol ?? ""),
    name: String(row.name ?? row.symbol ?? ""),
    profit_growth: Number(row.profit_growth) || 0,
    dividend_yield: Number(row.dividend_yield) || 0,
    roe: Number(row.roe) || 0,
    roa: row.roa == null || row.roa === "" ? null : Number(row.roa),
    pe_ratio: Number(row.pe_ratio) || 0,
    net_income: Number(row.net_income) || 0,
    matrix_score: Number(row.matrix_score) || 0,
    category: String(row.category ?? ""),
  };
}
