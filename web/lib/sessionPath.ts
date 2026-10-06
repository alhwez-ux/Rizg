export type SessionPath = "up" | "down";

export const PATH_UP_LABEL = "نوع المسار: صاعد ⬆️";
export const PATH_DOWN_LABEL = "نوع المسار: هابط ⬇️";

function finite(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Above a real VWAP, or a positive close when VWAP is absent. Flat or missing stays unlabeled. */
export function sessionPath(input: {
  price?: number | null;
  vwap?: number | null;
  change?: number | null;
}): SessionPath | null {
  const price = finite(input.price);
  const vwap = finite(input.vwap);
  if (price != null && price > 0 && vwap != null && vwap > 0) {
    return price >= vwap ? "up" : "down";
  }
  const change = finite(input.change);
  if (change != null && change !== 0) return change > 0 ? "up" : "down";
  return null;
}
