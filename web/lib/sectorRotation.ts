import { apiFetch } from "@/lib/api";
import { readLiveCache, writeLiveCache } from "@/lib/liveCache";
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
  source?: string;
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
  const key = `sector-companies:${sector.trim()}`;
  const cached = readLiveCache<SectorCompaniesResponse>(key);
  try {
    const encoded = encodeURIComponent(sector.trim());
    const response = await apiFetch(`/api/v1/market/sector-companies/${encoded}`, {
      method: "GET",
    });
    const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
    if (!response.ok) {
      return cached ?? emptySectorCompanies(sector);
    }
    const rows = Array.isArray(payload?.companies) ? payload.companies : [];
    const companies = rows.map((row) => parseCompany(row));
    const result: SectorCompaniesResponse = {
      success: true,
      sector: String(payload?.sector ?? sector),
      total_companies: Number(payload?.total_companies) || companies.length,
      companies,
    };
    if (companies.some((row) => row.live)) {
      writeLiveCache(key, result);
      return result;
    }
    if (cached?.companies?.some((row) => row.live)) {
      return cached;
    }
    return result;
  } catch {
    return cached ?? emptySectorCompanies(sector);
  }
}

function emptySectorCompanies(sector: string): SectorCompaniesResponse {
  return { success: true, sector, total_companies: 0, companies: [] };
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
  const cached = readLiveCache<SectorRotationResponse>("sector-rotation");
  try {
    const response = await apiFetch("/api/v1/market/sector-rotation", {
      method: "GET",
    });
    const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
    if (!response.ok) {
      return cached ?? emptySectors();
    }
    const rows = Array.isArray(payload?.sectors)
      ? payload.sectors
      : Array.isArray(payload?.data)
        ? payload.data
        : [];
    const sectors = rows.map((row, index) => parseSector(row, index));
    const result: SectorRotationResponse = {
      success: true,
      total_sectors: Number(payload?.total_sectors) || sectors.length,
      source: String(payload?.source ?? "Sahm API"),
      sectors,
    };
    if (sectors.length && sectors.some((row) => row.total_value_traded > 0 || row.total_volume > 0)) {
      writeLiveCache("sector-rotation", result);
      return result;
    }
    if (cached?.sectors?.length) {
      return { ...cached, source: "cached" };
    }
    return result;
  } catch {
    return cached ?? emptySectors();
  }
}

function emptySectors(): SectorRotationResponse {
  return { success: true, total_sectors: 0, source: "Sahm API", sectors: [] };
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
