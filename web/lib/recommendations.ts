import { apiFetch } from "@/lib/api";
import { readLiveCache, writeLiveCache } from "@/lib/liveCache";
import { toFiniteNumber } from "@/lib/screener";

const CACHE_KEY = "recommendations";

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
  const cached = readLiveCache<RecommendationsResponse>(CACHE_KEY);
  try {
    const response = await apiFetch("/api/v1/market/recommendations", { method: "GET" });
    const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
    if (!response.ok) {
      return cached ?? emptyRecommendations();
    }
    const rows = Array.isArray(payload?.data) ? payload.data : [];
    const data = rows.map((row) => parseRecommendation(row)).filter((row) => row.close_price > 0);
    const result: RecommendationsResponse = {
      success: true,
      count: Number(payload?.count) || data.length,
      source: String(payload?.source ?? "Sahm API"),
      data,
    };
    if (data.length) {
      writeLiveCache(CACHE_KEY, result);
      return result;
    }
    if (cached?.data?.length) {
      return { ...cached, source: "cached" };
    }
    return result;
  } catch {
    return cached ?? emptyRecommendations();
  }
}

function emptyRecommendations(): RecommendationsResponse {
  return { success: true, count: 0, source: "Sahm API", data: [] };
}

function parseRecommendation(raw: unknown): MarketRecommendation {
  const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const kind = row.signal_kind === "bounce" ? "bounce" : "momentum";
  return {
    symbol: String(row.symbol ?? ""),
    name: String(row.name ?? row.symbol ?? ""),
    close_price: toFiniteNumber(row.close_price) ?? 0,
    signal_type: String(row.signal_type ?? ""),
    signal_kind: kind,
    confidence: String(row.confidence ?? ""),
    confidence_score: toFiniteNumber(row.confidence_score) ?? 0,
    entry_price: String(row.entry_price ?? ""),
    target_price: String(row.target_price ?? ""),
    stop_loss: String(row.stop_loss ?? ""),
    reason: String(row.reason ?? ""),
    volume_ratio: toFiniteNumber(row.volume_ratio),
    mfi: toFiniteNumber(row.mfi),
  };
}
