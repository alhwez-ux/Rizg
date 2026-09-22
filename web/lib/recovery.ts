import { apiFetch } from "@/lib/api";
import { toFiniteNumber } from "@/lib/screener";

export interface RecoveryPosition {
  symbol: string;
  name: string;
  sector: string;
  quantity: number;
  avg_price: number;
  last_price: number;
  cost_basis: number;
  market_value: number;
  unrealized_pnl: number;
  loss_amount: number;
  pnl_pct: number;
  in_loss: boolean;
}

export interface RecoveryAverage {
  recommended: boolean;
  extra_quantity: number;
  extra_cost: number;
  new_quantity: number;
  new_avg_price: number;
  entry: number;
  target: number;
  stop: number;
  reason: string;
}

export interface RecoveryAllocation {
  symbol: string;
  name: string;
  sector: string;
  score: number;
  tags: string[];
  weight_pct: number;
  allocation: number;
  shares: number;
  entry: number;
  target: number;
  stop: number;
  expected_gain: number;
  reason: string;
}

export interface RecoveryPlanResponse {
  success: boolean;
  session_phase: string;
  session_label: string;
  source: string;
  stance: string;
  stance_label: string;
  hint: string;
  scanned_at: string;
  position: RecoveryPosition;
  averaging: RecoveryAverage | null;
  rotation_budget: number;
  expected_recovery: number;
  cover_pct: number;
  count: number;
  data: RecoveryAllocation[];
}

function parseAverage(raw: unknown): RecoveryAverage | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const extra = Math.max(0, Math.round(toFiniteNumber(row.extra_quantity) ?? 0));
  const entry = toFiniteNumber(row.entry);
  const target = toFiniteNumber(row.target);
  const stop = toFiniteNumber(row.stop);
  if (!extra || entry == null || target == null || stop == null) return null;
  return {
    recommended: Boolean(row.recommended ?? true),
    extra_quantity: extra,
    extra_cost: toFiniteNumber(row.extra_cost) ?? 0,
    new_quantity: toFiniteNumber(row.new_quantity) ?? extra,
    new_avg_price: toFiniteNumber(row.new_avg_price) ?? entry,
    entry,
    target,
    stop,
    reason: String(row.reason ?? ""),
  };
}

function parseAllocation(raw: unknown): RecoveryAllocation | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  if (!/^\d{4}$/.test(symbol)) return null;
  const entry = toFiniteNumber(row.entry);
  const target = toFiniteNumber(row.target);
  const stop = toFiniteNumber(row.stop);
  if (entry == null || target == null || stop == null) return null;
  return {
    symbol,
    name: String(row.name ?? symbol),
    sector: String(row.sector ?? ""),
    score: toFiniteNumber(row.score) ?? 0,
    tags: Array.isArray(row.tags) ? row.tags.map(String) : [],
    weight_pct: toFiniteNumber(row.weight_pct) ?? 0,
    allocation: toFiniteNumber(row.allocation) ?? 0,
    shares: Math.max(0, Math.round(toFiniteNumber(row.shares) ?? 0)),
    entry,
    target,
    stop,
    expected_gain: toFiniteNumber(row.expected_gain) ?? 0,
    reason: String(row.reason ?? ""),
  };
}

function parsePosition(raw: unknown): RecoveryPosition | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  if (!/^\d{4}$/.test(symbol)) return null;
  return {
    symbol,
    name: String(row.name ?? symbol),
    sector: String(row.sector ?? ""),
    quantity: toFiniteNumber(row.quantity) ?? 0,
    avg_price: toFiniteNumber(row.avg_price) ?? 0,
    last_price: toFiniteNumber(row.last_price) ?? 0,
    cost_basis: toFiniteNumber(row.cost_basis) ?? 0,
    market_value: toFiniteNumber(row.market_value) ?? 0,
    unrealized_pnl: toFiniteNumber(row.unrealized_pnl) ?? 0,
    loss_amount: toFiniteNumber(row.loss_amount) ?? 0,
    pnl_pct: toFiniteNumber(row.pnl_pct) ?? 0,
    in_loss: Boolean(row.in_loss),
  };
}

function readError(payload: Record<string, unknown> | null, fallback: string): string {
  if (!payload) return fallback;
  if (typeof payload.message === "string" && payload.message.trim()) return payload.message;
  if (typeof payload.detail === "string" && payload.detail.trim()) return payload.detail;
  return fallback;
}

export async function fetchRecoveryPlan(input: {
  symbol: string;
  quantity: number;
  avg_price: number;
}): Promise<RecoveryPlanResponse> {
  const response = await apiFetch("/api/v1/recovery/plan", {
    method: "POST",
    body: JSON.stringify(input),
    timeoutMs: 45_000,
  });
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    throw new Error(readError(payload, "تعذر حساب خطة التعديل"));
  }
  const position = parsePosition(payload?.position);
  if (!position) {
    throw new Error("تعذر قراءة مركز الخسارة");
  }
  const rows = Array.isArray(payload?.data) ? payload.data : [];
  return {
    success: Boolean(payload?.success ?? true),
    session_phase: String(payload?.session_phase ?? ""),
    session_label: String(payload?.session_label ?? ""),
    source: String(payload?.source ?? "TickChart"),
    stance: String(payload?.stance ?? ""),
    stance_label: String(payload?.stance_label ?? ""),
    hint: String(payload?.hint ?? ""),
    scanned_at: payload?.scanned_at == null ? "" : String(payload.scanned_at),
    position,
    averaging: parseAverage(payload?.averaging),
    rotation_budget: toFiniteNumber(payload?.rotation_budget) ?? 0,
    expected_recovery: toFiniteNumber(payload?.expected_recovery) ?? 0,
    cover_pct: toFiniteNumber(payload?.cover_pct) ?? 0,
    count: toFiniteNumber(payload?.count) ?? rows.length,
    data: rows.map(parseAllocation).filter((row): row is RecoveryAllocation => row != null),
  };
}
