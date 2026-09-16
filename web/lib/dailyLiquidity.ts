import { apiFetch } from "@/lib/api";

export type LiquidityGrade = "A" | "B" | "C" | "D";

export interface DailyLiquidityRow {
  rank: number;
  symbol: string;
  name: string;
  last_price: number | null;
  price_change_pct: number;
  net_flow: number;
  inflow: number;
  volume: number;
  value_traded: number;
  grade: LiquidityGrade;
}

type RawRow = Omit<DailyLiquidityRow, "rank" | "grade">;

function parseRow(item: Record<string, unknown>): RawRow | null {
  const symbol = String(item.symbol || "").trim().toUpperCase();
  if (symbol.length !== 4) return null;
  const price = Number(item.last_price ?? item.price);
  const netFlow = Number(item.net_flow) || 0;
  const inflowRaw = Number(item.inflow);
  const inflow = Number.isFinite(inflowRaw) && inflowRaw > 0 ? inflowRaw : Math.max(netFlow, 0);
  return {
    symbol,
    name: String(item.name || symbol),
    last_price: Number.isFinite(price) && price > 0 ? price : null,
    price_change_pct: Number(item.price_change_pct ?? item.change_percent) || 0,
    net_flow: netFlow,
    inflow,
    volume: Number(item.volume) || 0,
    value_traded: Number(item.value_traded) || 0,
  };
}

export function gradeDailyLiquidity(rows: RawRow[]): DailyLiquidityRow[] {
  const sorted = [...rows].sort((left, right) => {
    const inflowDelta = right.inflow - left.inflow;
    if (inflowDelta !== 0) return inflowDelta;
    return right.net_flow - left.net_flow;
  });
  const winners = sorted.filter((row) => row.net_flow > 0);
  const aCount = winners.length ? Math.max(1, Math.ceil(winners.length * 0.2)) : 0;
  const bCount = winners.length ? Math.max(aCount, Math.ceil(winners.length * 0.5)) : 0;
  const gradeA = new Set(winners.slice(0, aCount).map((row) => row.symbol));
  const gradeB = new Set(winners.slice(0, bCount).map((row) => row.symbol));

  return sorted.map((row, index) => {
    let grade: LiquidityGrade = "C";
    if (row.net_flow <= 0) grade = "D";
    else if (gradeA.has(row.symbol)) grade = "A";
    else if (gradeB.has(row.symbol)) grade = "B";
    return { ...row, rank: index + 1, grade };
  });
}

async function loadPath(path: string): Promise<RawRow[]> {
  try {
    const response = await apiFetch(path, { timeoutMs: 60_000 });
    const payload = (await response.json().catch(() => null)) as { data?: unknown } | null;
    if (!response.ok || !payload || !Array.isArray(payload.data)) return [];
    return payload.data
      .map((row) => parseRow(row as Record<string, unknown>))
      .filter((row): row is RawRow => row != null);
  } catch {
    return [];
  }
}

export async function fetchDailyLiquidity(): Promise<DailyLiquidityRow[]> {
  const market = await loadPath("/api/v1/tickchart/market");
  const rows = market.length ? market : await loadPath("/api/v1/tickchart/tape");
  return gradeDailyLiquidity(rows);
}
