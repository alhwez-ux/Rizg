/** How long a radar screen stays fixed before it may change. */
export const RADAR_DISPLAY_MS = 60_000;
const RADAR_DISPLAY_LIMIT = 12;

export interface HeldRow<T> {
  symbol: string;
  row: T;
  shownAt: number;
}

export function holdDisplayedRows<T extends { symbol: string }>(
  previous: HeldRow<T>[],
  incoming: T[],
  now: number,
  holdMs = RADAR_DISPLAY_MS,
  limit = RADAR_DISPLAY_LIMIT,
): HeldRow<T>[] {
  const incomingBySymbol = new Map(incoming.map((row) => [row.symbol, row]));
  const next: HeldRow<T>[] = [];
  const seen = new Set<string>();

  for (const held of previous) {
    const fresh = incomingBySymbol.get(held.symbol);
    const mature = now - held.shownAt >= holdMs;
    if (fresh) {
      next.push(mature ? { symbol: held.symbol, row: fresh, shownAt: now } : held);
      seen.add(held.symbol);
      continue;
    }
    if (!mature) {
      next.push(held);
      seen.add(held.symbol);
    }
  }

  for (const row of incoming) {
    if (seen.has(row.symbol) || next.length >= limit) continue;
    next.push({ symbol: row.symbol, row, shownAt: now });
  }
  return next;
}

export function nextDisplayWake<T>(held: HeldRow<T>[], now: number, holdMs = RADAR_DISPLAY_MS): number | null {
  let wait: number | null = null;
  for (const item of held) {
    const remaining = holdMs - (now - item.shownAt);
    if (remaining <= 0) return 0;
    if (wait == null || remaining < wait) wait = remaining;
  }
  return wait;
}
