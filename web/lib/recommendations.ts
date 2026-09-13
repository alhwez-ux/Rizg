import { recommendationsFromMarket } from "@/lib/marketEngine";
import { loadTasiTape } from "@/lib/tadawulCloses";

export type RecommendationKind = "bounce" | "momentum";

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
}

export interface RecommendationsResponse {
  success: boolean;
  count: number;
  source: string;
  data: MarketRecommendation[];
}

export async function fetchMarketRecommendations(): Promise<RecommendationsResponse> {
  const tape = await loadTasiTape();
  return recommendationsFromMarket(tape.rows, tape.source);
}
