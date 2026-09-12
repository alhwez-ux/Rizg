import type { ComplianceStatus } from "@prisma/client";

export const RADAR_ELIGIBLE_STATUSES: readonly ["PURE", "MIXED"] = ["PURE", "MIXED"];

export interface PurificationResult {
  status: "PURE" | "MIXED";
  rate: number;
  applied: boolean;
  due: number;
  net: number;
}

function clampRate(rate: number): number {
  if (!Number.isFinite(rate) || rate <= 0) return 0;
  if (rate > 1) return 1;
  return rate;
}

/**
 * Apply the Shariah purification rate to a gross cash amount (e.g. dividend).
 * PURE: nothing is purified. MIXED: `due = gross * rate`, `net = gross - due`.
 * PROHIBITED names must never reach this function.
 */
export function applyPurification(
  grossAmount: number,
  status: ComplianceStatus,
  purificationRate: number,
): PurificationResult | null {
  if (status === "PROHIBITED") return null;

  const gross = Number.isFinite(grossAmount) ? grossAmount : 0;

  if (status === "PURE") {
    return { status: "PURE", rate: 0, applied: false, due: 0, net: gross };
  }

  const rate = clampRate(purificationRate);
  const due = gross * rate;
  return {
    status: "MIXED",
    rate,
    applied: rate > 0,
    due,
    net: gross - due,
  };
}
