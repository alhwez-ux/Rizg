import { apiFetch, HEAVY_API_TIMEOUT_MS } from "@/lib/api";
import { isValidLongPlan } from "@/lib/tradeGeometry";

export type RecommendationKind = "bounce" | "momentum";
export type RecommendationScanMode = "live" | "end_of_day";

export interface MarketRecommendation {
  symbol: string;
  name: string;
  close_price: number;
  last_price?: number | null;
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
  entry_locked_at?: string | null;
  target_hit?: boolean;
  stop_hit?: boolean;
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
  const data = (payload.data || []).filter(
    (row) =>
      !row.target_hit &&
      !row.stop_hit &&
      isValidLongPlan(row.entry_price || row.close_price, row.target_price, row.stop_loss),
  );
  return { ...payload, data, count: data.length };
}

export type FrozenEntry = {
  entry_price: string;
  target_price: string;
  stop_loss: string;
  locked_at: string;
};

export function recommendationResolved(
  row: Pick<MarketRecommendation, "last_price" | "close_price" | "target_price" | "stop_loss" | "target_hit" | "stop_hit">,
  lastOverride?: number | null,
): boolean {
  if (row.target_hit || row.stop_hit) return true;
  const last = Number(lastOverride ?? row.last_price ?? row.close_price);
  const target = Number(row.target_price);
  const stop = Number(row.stop_loss);
  if (Number.isFinite(last) && Number.isFinite(target) && last >= target) return true;
  if (Number.isFinite(last) && Number.isFinite(stop) && last <= stop) return true;
  return false;
}

export function freezeRecommendationEntry(
  incoming: MarketRecommendation,
  previous: FrozenEntry | undefined,
): { row: MarketRecommendation; lock: FrozenEntry } {
  const lock = previous ?? {
    entry_price: incoming.entry_price,
    target_price: incoming.target_price,
    stop_loss: incoming.stop_loss,
    locked_at: incoming.entry_locked_at || new Date().toISOString(),
  };
  const last = Number(incoming.last_price ?? incoming.close_price);
  const target = Number(lock.target_price);
  const stop = Number(lock.stop_loss);
  return {
    lock,
    row: {
      ...incoming,
      entry_price: lock.entry_price,
      target_price: lock.target_price,
      stop_loss: lock.stop_loss,
      entry_locked_at: lock.locked_at,
      target_hit: Number.isFinite(last) && Number.isFinite(target) && last >= target,
      stop_hit: Number.isFinite(last) && Number.isFinite(stop) && last <= stop,
    },
  };
}

export function riyadhSessionDate(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Riyadh" }).format(now);
}
