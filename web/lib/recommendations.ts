import { apiFetch, HEAVY_API_TIMEOUT_MS } from "@/lib/api";

export type RecommendationKind = "bounce" | "momentum";
export type RecommendationScanMode = "live" | "end_of_day";

export interface MarketRecommendation {
  symbol: string;
  name: string;
  close_price: number;
  signal_type: string;
  signal_kind: RecommendationKind;
  confidence: string;
  confidence_score: number;
  entry_price: string;
  target_price: string;
  stop_loss: string;
  reason: string;
  volume_ratio: number | null;
  mfi: number | null;
  scan_mode?: RecommendationScanMode | string | null;
  horizon?: string | null;
  entry?: boolean;
  entry_rule?: string | null;
}

export interface RecommendationsResponse {
  success: boolean;
  count: number;
  total?: number;
  source: string;
  scan_mode?: RecommendationScanMode | string;
  session_phase?: string;
  session_label?: string;
  data: MarketRecommendation[];
}

let inflight: Promise<RecommendationsResponse> | null = null;

export async function fetchMarketRecommendations(): Promise<RecommendationsResponse> {
  if (inflight) return inflight;
  inflight = pullMarketRecommendations().finally(() => {
    inflight = null;
  });
  return inflight;
}

async function pullMarketRecommendations(): Promise<RecommendationsResponse> {
  const response = await apiFetch("/api/v1/market/recommendations", {
    timeoutMs: HEAVY_API_TIMEOUT_MS,
  });
  const payload = (await response.json().catch(() => null)) as RecommendationsResponse | null;
  if (!response.ok || !payload) {
    throw new Error("تعذر جلب التوصيات");
  }
  return payload;
}
