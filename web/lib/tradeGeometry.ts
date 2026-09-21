/** Long/BUY safety: Target must sit strictly above entry, stop strictly below. */

export function isValidLongPlan(
  entry: number | string | null | undefined,
  target: number | string | null | undefined,
  stop: number | string | null | undefined,
): boolean {
  const price = Number(entry);
  const targetPrice = Number(target);
  const stopPrice = Number(stop);
  return (
    Number.isFinite(price) &&
    Number.isFinite(targetPrice) &&
    Number.isFinite(stopPrice) &&
    targetPrice > price &&
    price > stopPrice &&
    stopPrice > 0
  );
}
