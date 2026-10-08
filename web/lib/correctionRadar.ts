import { apiFetch } from "@/lib/api";
import { toFiniteNumber } from "@/lib/screener";

export type CorrectionKind = "approach" | "rebound";

export interface CorrectionRadarRow {
  symbol: string;
  name: string;
  sector: string;
  last_price: number | null;
  signal: string;
  signal_kind: CorrectionKind;
  reasons: string[];
  pillars: number;
}

export interface CorrectionRadarResponse {
  success: boolean;
  session_phase: string;
  session_label: string;
  source: string;
  count: number;
  approach_count: number;
  rebound_count: number;
  hint: string;
  scanned_at: string;
  data: CorrectionRadarRow[];
}

function parseKind(value: unknown): CorrectionKind | null {
  if (value === "approach" || value === "rebound") return value;
  return null;
}

export function parseCorrectionRow(raw: unknown): CorrectionRadarRow | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  const kind = parseKind(row.signal_kind);
  if (!/^\d{4}$/.test(symbol) || !kind) return null;
  const reasons = Array.isArray(row.reasons) ? row.reasons.map((item) => String(item)).filter(Boolean) : [];
  return {
    symbol,
    name: String(row.name ?? symbol),
    sector: String(row.sector ?? ""),
    last_price: toFiniteNumber(row.last_price),
    signal: String(row.signal ?? ""),
    signal_kind: kind,
    reasons,
    pillars: Math.max(0, Math.round(toFiniteNumber(row.pillars) ?? reasons.length)),
  };
}

export function parseCorrectionRadar(payload: Record<string, unknown> | null): CorrectionRadarResponse {
  const rows = Array.isArray(payload?.data) ? payload.data : [];
  const data = rows.map(parseCorrectionRow).filter((row): row is CorrectionRadarRow => row != null);
  return {
    success: Boolean(payload?.success ?? true),
    session_phase: String(payload?.session_phase ?? ""),
    session_label: String(payload?.session_label ?? ""),
    source: String(payload?.source ?? "TickChart"),
    count: toFiniteNumber(payload?.count) ?? data.length,
    approach_count: toFiniteNumber(payload?.approach_count) ?? data.filter((row) => row.signal_kind === "approach").length,
    rebound_count: toFiniteNumber(payload?.rebound_count) ?? data.filter((row) => row.signal_kind === "rebound").length,
    hint: String(payload?.hint ?? ""),
    scanned_at: payload?.scanned_at == null ? "" : String(payload.scanned_at),
    data,
  };
}

export async function fetchCorrectionRadar(): Promise<CorrectionRadarResponse> {
  const response = await apiFetch("/api/v1/correction-radar/scan", { timeoutMs: 45_000 });
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok || !payload) {
    throw new Error("تعذر جلب منبه التصحيح");
  }
  return parseCorrectionRadar(payload);
}
