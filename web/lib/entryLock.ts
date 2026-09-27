import { isValidLongPlan } from "@/lib/tradeGeometry";

export interface ClientEntryLock {
  entry_price: string;
  target_price: string;
  stop_loss: string;
  reward_ratio: number;
}

const STORAGE_KEY = "rizg-live-entry-locks";

function readLocks(): Record<string, ClientEntryLock> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, ClientEntryLock>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeLocks(locks: Record<string, ClientEntryLock>) {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(locks));
  } catch {
    /* private mode */
  }
}

/** Keep the first plan the screen showed. Refreshing last price must not move entry, target, or stop. */
export function rememberClientLock(scope: string, symbol: string, plan: ClientEntryLock): ClientEntryLock {
  if (!isValidLongPlan(plan.entry_price, plan.target_price, plan.stop_loss)) return plan;
  if (typeof window === "undefined") return plan;
  const locks = readLocks();
  const key = `${scope}:${symbol}`;
  const existing = locks[key];
  if (existing && isValidLongPlan(existing.entry_price, existing.target_price, existing.stop_loss)) {
    return existing;
  }
  locks[key] = plan;
  writeLocks(locks);
  return plan;
}
