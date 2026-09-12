export type MarketTone = "up" | "down" | "flat";

export const TASI_UP_FILL = "#10B981";
export const TASI_DOWN_FILL = "#F43F5E";

export function toneFromChange(change: number | null | undefined): MarketTone {
  if (change == null || !Number.isFinite(change) || change === 0) return "flat";
  return change > 0 ? "up" : "down";
}
