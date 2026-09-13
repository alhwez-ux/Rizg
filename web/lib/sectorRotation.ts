import { toFiniteNumber } from "@/lib/screener";

export interface SectorData {
  sector: string;
  total_value_traded: number;
  avg_price_change: number;
  total_volume: number;
  companies_count: number;
  sector_momentum_score: number;
  status: string;
  net_flow: number;
  rank: number;
}

export interface SectorRotationResponse {
  success: boolean;
  total_sectors: number;
  sectors: SectorData[];
}

export interface SectorCompany {
  symbol: string;
  name: string;
  sector: string;
  price_change_pct: number;
  volume: number;
  value_traded: number;
  net_flow: number;
  inflow: number;
  outflow: number;
  flow_status: string;
  live: boolean;
}

export interface SectorCompaniesResponse {
  success: boolean;
  sector: string;
  total_companies: number;
  companies: SectorCompany[];
}

export async function fetchSectorCompanies(sector: string): Promise<SectorCompaniesResponse> {
  const encoded = encodeURIComponent(sector.trim());
  const response = await fetch(`/api/v1/market/sector-companies/${encoded}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : null;
    throw new Error(detail || "تعذر جلب شركات هذا القطاع");
  }
  const rows = Array.isArray(payload?.companies) ? payload.companies : [];
  return {
    success: Boolean(payload?.success ?? true),
    sector: String(payload?.sector ?? sector),
    total_companies: Number(payload?.total_companies) || rows.length,
    companies: rows.map((row) => parseCompany(row)),
  };
}

function parseCompany(raw: unknown): SectorCompany {
  const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    symbol: String(row.symbol ?? ""),
    name: String(row.name ?? row.symbol ?? ""),
    sector: String(row.sector ?? ""),
    price_change_pct: toFiniteNumber(row.price_change_pct) ?? 0,
    volume: toFiniteNumber(row.volume) ?? 0,
    value_traded: toFiniteNumber(row.value_traded) ?? 0,
    net_flow: toFiniteNumber(row.net_flow) ?? 0,
    inflow: toFiniteNumber(row.inflow) ?? 0,
    outflow: toFiniteNumber(row.outflow) ?? 0,
    flow_status: String(row.flow_status ?? ""),
    live: Boolean(row.live),
  };
}

export async function fetchSectorRotation(): Promise<SectorRotationResponse> {
  const response = await fetch("/api/v1/market/sector-rotation", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : null;
    throw new Error(detail || "فشل في جلب بيانات تدوير السيولة القطاعية");
  }
  const rows = Array.isArray(payload?.sectors)
    ? payload.sectors
    : Array.isArray(payload?.data)
      ? payload.data
      : [];
  return {
    success: Boolean(payload?.success ?? true),
    total_sectors: Number(payload?.total_sectors) || rows.length,
    sectors: rows.map((row, index) => parseSector(row, index)),
  };
}

function parseSector(raw: unknown, index: number): SectorData {
  const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    sector: String(row.sector ?? ""),
    total_value_traded: toFiniteNumber(row.total_value_traded) ?? 0,
    avg_price_change: toFiniteNumber(row.avg_price_change) ?? 0,
    total_volume: toFiniteNumber(row.total_volume) ?? 0,
    companies_count: toFiniteNumber(row.companies_count) ?? 0,
    sector_momentum_score: toFiniteNumber(row.sector_momentum_score) ?? 0,
    status: String(row.status ?? ""),
    net_flow: toFiniteNumber(row.net_flow) ?? 0,
    rank: toFiniteNumber(row.rank) ?? index + 1,
  };
}
