import { apiFetch } from "@/lib/api";

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
  quote_mode?: "live" | "last_close" | "waiting" | string;
  sectors: SectorData[];
}

export interface SectorCompany {
  symbol: string;
  name: string;
  sector: string;
  last_price: number | null;
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
  const response = await apiFetch(`/api/v1/market/sector-companies/${encodeURIComponent(sector)}`, {
    timeoutMs: 60_000,
  });
  const payload = (await response.json().catch(() => null)) as SectorCompaniesResponse | null;
  if (!response.ok || !payload) {
    throw new Error("تعذر جلب شركات القطاع من تكرتشارت");
  }
  return payload;
}

export async function fetchSectorRotation(): Promise<SectorRotationResponse> {
  const response = await apiFetch("/api/v1/market/sector-rotation", { timeoutMs: 60_000 });
  const payload = (await response.json().catch(() => null)) as SectorRotationResponse | null;
  if (!response.ok || !payload) {
    throw new Error("تعذر جلب خريطة القطاعات من تكرتشارت");
  }
  return payload;
}
