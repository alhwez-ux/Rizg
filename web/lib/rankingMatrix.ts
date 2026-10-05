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

const RANK_CACHE_MS = 5 * 60_000;
let rankCache: { at: number; rows: RankingRow[] } | null = null;
let rankInflight: Promise<RankingRow[]> | null = null;

async function loadRanks(): Promise<RankingRow[]> {
  if (rankCache && Date.now() - rankCache.at < RANK_CACHE_MS) return rankCache.rows;
  if (!rankInflight) {
    rankInflight = fetchRankingMatrix()
      .then((payload) => {
        const rows = payload.data ?? [];
        rankCache = { at: Date.now(), rows };
        return rows;
      })
      .finally(() => {
        rankInflight = null;
      });
  }
  return rankInflight;
}

export async function companyRankFor(symbol: string): Promise<RankingRow | null> {
  const key = symbol.trim().toUpperCase();
  if (!key) return null;
  const rows = await loadRanks();
  return rows.find((row) => row.symbol.trim().toUpperCase() === key) ?? null;
}

export function strengthTone(category: string): "strong" | "steady" | "mid" | "weak" | "risk" {
  if (category.includes("قلاع")) return "strong";
  if (category.includes("واعدة")) return "steady";
  if (category.includes("خاسر") || category.includes("مخاطر")) return "risk";
  if (category.includes("ضعيف")) return "weak";
  return "mid";
}
