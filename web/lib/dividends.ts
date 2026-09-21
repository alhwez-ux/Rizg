import { apiFetch } from "@/lib/api";
import { toFiniteNumber } from "@/lib/screener";

export interface DividendRow {
  symbol: string;
  name: string;
  sector: string;
  cash_dividend: number;
  eligibility_date: string;
  payment_date: string;
  shariah_status: string | null;
  shariah_label: string;
  days_to_eligibility: number;
}

export interface DividendsResponse {
  success: boolean;
  count: number;
  as_of: string;
  timezone: string;
  hint: string;
  data: DividendRow[];
}

export async function fetchActiveDividends(pureOnly = false): Promise<DividendsResponse> {
  const query = pureOnly ? "?pure_only=true" : "";
  const response = await apiFetch(`/api/v1/market/dividends${query}`);
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    throw new Error(readError(payload, "تعذر جلب أخبار الأرباح والتوزيعات"));
  }
  return parseDividends(payload);
}

export function parseDividends(payload: Record<string, unknown> | null): DividendsResponse {
  const rows = Array.isArray(payload?.data) ? payload.data : [];
  return {
    success: Boolean(payload?.success ?? true),
    count: toFiniteNumber(payload?.count) ?? rows.length,
    as_of: payload?.as_of == null ? "" : String(payload.as_of),
    timezone: String(payload?.timezone ?? "Asia/Riyadh"),
    hint: String(payload?.hint ?? ""),
    data: rows
      .map((item) => parseDividendRow(item))
      .filter((row): row is DividendRow => row != null),
  };
}

export function parseDividendRow(raw: unknown): DividendRow | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const symbol = String(row.symbol ?? "").trim().toUpperCase();
  if (!/^\d{4}$/.test(symbol)) return null;
  const cash = toFiniteNumber(row.cash_dividend);
  if (cash == null || cash <= 0) return null;
  return {
    symbol,
    name: String(row.name ?? symbol),
    sector: String(row.sector ?? ""),
    cash_dividend: cash,
    eligibility_date: String(row.eligibility_date ?? "").slice(0, 10),
    payment_date: String(row.payment_date ?? "").slice(0, 10),
    shariah_status: row.shariah_status == null ? null : String(row.shariah_status),
    shariah_label: String(row.shariah_label ?? ""),
    days_to_eligibility: toFiniteNumber(row.days_to_eligibility) ?? 0,
  };
}

export function formatRiyadhDate(iso: string): string {
  const stamp = iso.slice(0, 10);
  const [year, month, day] = stamp.split("-");
  if (!year || !month || !day) return iso || "—";
  return `${day}/${month}/${year}`;
}

function readError(payload: Record<string, unknown> | null, fallback: string): string {
  if (!payload) return fallback;
  if (typeof payload.message === "string" && payload.message.trim()) return payload.message;
  if (typeof payload.detail === "string" && payload.detail.trim()) return payload.detail;
  return fallback;
}
