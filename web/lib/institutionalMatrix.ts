import { formatMoney } from "@/lib/liquidity";
import { passesShariahFilter, type ShariahFilter } from "@/lib/shariah";
import type { ScreenerRow } from "@/lib/screener";
import type { SmartMoneyRow } from "@/lib/smartMoney";

export interface BoardCard {
  symbol: string;
  name: string;
  price: number | null;
  metric: string;
  reason: string;
  score: number;
}

const COLUMN_LIMIT = 8;

function allowed(symbol: string, filter: ShariahFilter): boolean {
  return passesShariahFilter(symbol, filter);
}

function byScore(left: BoardCard, right: BoardCard): number {
  return right.score - left.score || left.symbol.localeCompare(right.symbol);
}

function statedReason(reasons: string[], fallback: string): string {
  const paper = reasons.find((item) => /الورقة|مكرر الربحية|صافي الدخل|دين الفائدة/.test(item));
  return paper || reasons.find((item) => item.trim()) || fallback;
}

export function entryBoard(rows: ScreenerRow[], filter: ShariahFilter): BoardCard[] {
  return rows
    .filter((row) => row.entry_signal && !row.exit_signal && allowed(row.symbol, filter))
    .map((row) => ({
      symbol: row.symbol,
      name: row.name || row.symbol,
      price: row.price > 0 ? row.price : null,
      metric: formatMoney(row.net_flow),
      reason: statedReason(row.reasons, "دخول بعد توافق السيولة والكتل ومتوسط 15 دقيقة"),
      score: row.score,
    }))
    .sort(byScore)
    .slice(0, COLUMN_LIMIT);
}

export function exitBoard(rows: ScreenerRow[], filter: ShariahFilter): BoardCard[] {
  return rows
    .filter((row) => row.exit_signal && !row.entry_signal && allowed(row.symbol, filter))
    .map((row) => ({
      symbol: row.symbol,
      name: row.name || row.symbol,
      price: row.price > 0 ? row.price : null,
      metric: formatMoney(row.net_flow),
      reason: statedReason(row.reasons, "خروج بعد انعكاس السيولة والكتل ومتوسط 15 دقيقة"),
      score: row.score,
    }))
    .sort(byScore)
    .slice(0, COLUMN_LIMIT);
}

function moneyCard(row: SmartMoneyRow): BoardCard {
  return {
    symbol: row.symbol,
    name: row.name || row.symbol,
    price: row.last_price,
    metric: Math.round(row.institutional_flow_score).toLocaleString("en-US"),
    reason: row.reason || row.badge,
    score: row.institutional_flow_score,
  };
}

export function accumulationBoard(rows: SmartMoneyRow[], filter: ShariahFilter): BoardCard[] {
  return rows
    .filter((row) => row.signal_kind === "accumulation" && row.plan_ok && allowed(row.symbol, filter))
    .map(moneyCard)
    .sort(byScore)
    .slice(0, COLUMN_LIMIT);
}

export function distributionBoard(rows: SmartMoneyRow[], filter: ShariahFilter): BoardCard[] {
  return rows
    .filter((row) => row.signal_kind === "distribution" && allowed(row.symbol, filter))
    .map(moneyCard)
    .sort(byScore)
    .slice(0, COLUMN_LIMIT);
}
