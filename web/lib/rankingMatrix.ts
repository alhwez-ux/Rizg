import { rankingFromMarket } from "@/lib/marketEngine";

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
  return rankingFromMarket();
}
