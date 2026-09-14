import { apiFetch } from "@/lib/api";

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
  last_price: number | null;
  volume: number | null;
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
  const response = await apiFetch("/api/v1/market/ranking-matrix", { timeoutMs: 60_000 });
  const payload = (await response.json().catch(() => null)) as RankingMatrixResponse | null;
  if (!response.ok || !payload) {
    throw new Error("تعذر جلب مصفوفة التصنيف من تكرتشارت");
  }
  return payload;
}
