import { apiFetch } from "@/lib/api";
import { toFiniteNumber } from "@/lib/screener";

export type CloudPosition = "above" | "inside" | "below";
export type IchimokuSignal = "entry" | "exit" | "watch";

export interface DigitalTapeRow {
  symbol: string;
  name: string;
  price: number | null;
  change: number | null;
  vwap: number | null;
  blocks: number | null;
  blockSide: "buy" | "sell" | null;
  netFlow: number | null;
  institutionalMfi: number | null;
  signal: string | null;
  hiddenAccumulation: boolean;
  path: "up" | "down" | "range" | null;
  cloud: CloudPosition | null;
  cloudSignal: IchimokuSignal | null;
}

function parsePath(value: unknown): DigitalTapeRow["path"] {
  if (value === "up" || value === "down" || value === "range") return value;
  return null;
}

function parseCloud(value: unknown): CloudPosition | null {
  if (value === "above" || value === "inside" || value === "below") return value;
  return null;
}

function parseCloudSignal(value: unknown): IchimokuSignal | null {
  if (value === "entry" || value === "exit" || value === "watch") return value;
  return null;
}

function parseSide(value: unknown): "buy" | "sell" | null {
  if (value === "buy" || value === "sell") return value;
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
    blockSide: parseSide(row.block_side),
    netFlow: toFiniteNumber(row.net_flow),
    institutionalMfi: toFiniteNumber(row.institutional_mfi ?? row.mfi),
    signal: typeof row.signal === "string" ? row.signal : null,
    hiddenAccumulation: row.hidden_accumulation === true,
    path: parsePath(row.ichimoku_trend),
    cloud: parseCloud(row.ichimoku_position),
    cloudSignal: parseCloudSignal(row.ichimoku_signal),
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
