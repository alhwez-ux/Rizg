import { apiFetch } from "@/lib/api";
import { toFiniteNumber } from "@/lib/screener";

export interface DigitalTapeRow {
  symbol: string;
  name: string;
  price: number | null;
  change: number | null;
  vwap: number | null;
  blocks: number | null;
  netFlow: number | null;
  path: "up" | "down" | "range" | null;
}

function parsePath(value: unknown): DigitalTapeRow["path"] {
  if (value === "up" || value === "down" || value === "range") return value;
  return null;
}

export function parseDigitalRow(raw: unknown): DigitalTapeRow | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  if (!/^\d{4}$/.test(symbol)) return null;
  const price = toFiniteNumber(row.last_price ?? row.price);
  const change = toFiniteNumber(row.price_change_pct ?? row.change_percent);
  return {
    symbol,
    name: String(row.name ?? symbol).trim() || symbol,
    price: price != null && price > 0 ? price : null,
    change,
    vwap: toFiniteNumber(row.session_vwap ?? row.vwap),
    blocks: toFiniteNumber(row.block_trades),
    netFlow: toFiniteNumber(row.net_flow),
    path: parsePath(row.ichimoku_trend),
  };
}

async function readRows(response: Response): Promise<DigitalTapeRow[]> {
  if (!response.ok) return [];
  const body = (await response.json()) as { data?: unknown };
  const list = Array.isArray(body.data) ? body.data : [];
  const rows: DigitalTapeRow[] = [];
  for (const item of list) {
    const parsed = parseDigitalRow(item);
    if (parsed) rows.push(parsed);
  }
  return rows;
}

/** One market read. Falls back to the tape book. Never throws. */
export async function fetchDigitalTape(): Promise<DigitalTapeRow[]> {
  try {
    const market = await apiFetch("/api/v1/tickchart/market", { timeoutMs: 60_000 });
    const rows = await readRows(market);
    if (rows.length) return rows;
  } catch {
    /* keep going to the tape */
  }
  try {
    const tape = await apiFetch("/api/v1/tickchart/tape", { timeoutMs: 60_000 });
    return await readRows(tape);
  } catch {
    return [];
  }
}
