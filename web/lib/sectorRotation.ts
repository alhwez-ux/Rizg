import { companiesFromMarket, sectorsFromMarket } from "@/lib/marketEngine";
import { loadTasiTape } from "@/lib/tadawulCloses";

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
  last_price: number;
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
  const tape = await loadTasiTape();
  return companiesFromMarket(sector, tape.rows);
}

export async function fetchSectorRotation(): Promise<SectorRotationResponse> {
  const tape = await loadTasiTape();
  return sectorsFromMarket(tape.rows, tape.source);
}
