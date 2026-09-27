import { isValidLongPlan } from "@/lib/tradeGeometry";

export interface ScaledLongPlan {
  entry_price: string;
  target_price: string;
  stop_loss: string;
  reward_ratio: number;
  locked_at: string;
}

const locks = new Map<string, ScaledLongPlan>();

function cents(value: number, mode: "up" | "down" | "near"): number {
  const scaled = Number((value * 100).toFixed(6));
  const rounded = mode === "up" ? Math.ceil(scaled) : mode === "down" ? Math.floor(scaled) : Math.round(scaled);
  return rounded / 100;
}

/** Move a valid long template onto a live entry without inverting target and stop. */
export function scaleLongPlan(
  templateEntry: number | string,
  templateTarget: number | string,
  templateStop: number | string,
  liveEntry: number | string,
): Omit<ScaledLongPlan, "locked_at"> | null {
  const base = Number(templateEntry);
  const templateGain = Number(templateTarget);
  const templateRisk = Number(templateStop);
  const live = Number(liveEntry);
  if (!isValidLongPlan(base, templateGain, templateRisk) || !(live > 0)) return null;
  const riskPct = (base - templateRisk) / base;
  const rewardPct = (templateGain - base) / base;
  if (!(riskPct > 0 && rewardPct > 0)) return null;
  const entry = cents(live, "near");
  let stop = cents(entry * (1 - riskPct), "down");
  let target = cents(entry * (1 + rewardPct), "up");
  if (stop >= entry) stop = cents(entry - 0.01, "near");
  if (target <= entry) target = cents(entry + 0.01, "near");
  if (!isValidLongPlan(entry, target, stop)) return null;
  const risk = entry - stop;
  return {
    entry_price: entry.toFixed(2),
    target_price: target.toFixed(2),
    stop_loss: stop.toFixed(2),
    reward_ratio: Math.round(((target - entry) / risk) * 100) / 100,
  };
}

/** First live print wins. Later prices update the tape, not the locked entry. */
export function lockScaledPlan(
  scope: string,
  symbol: string,
  horizon: string,
  templateEntry: number | string,
  templateTarget: number | string,
  templateStop: number | string,
  liveEntry: number | string,
  minReward = 0,
): ScaledLongPlan | null {
  const key = `${scope}:${symbol}:${horizon}`;
  const existing = locks.get(key);
  if (existing && isValidLongPlan(existing.entry_price, existing.target_price, existing.stop_loss)) {
    return existing;
  }
  const scaled = scaleLongPlan(templateEntry, templateTarget, templateStop, liveEntry);
  if (!scaled) return null;
  const lifted = minReward > 0 ? liftReward(scaled, minReward) : scaled;
  if (!lifted || !isValidLongPlan(lifted.entry_price, lifted.target_price, lifted.stop_loss)) return null;
  const locked = { ...lifted, locked_at: new Date().toISOString() };
  locks.set(key, locked);
  return locked;
}

function liftReward(plan: Omit<ScaledLongPlan, "locked_at">, minReward: number) {
  if (plan.reward_ratio >= minReward) return plan;
  const entry = Number(plan.entry_price);
  const stop = Number(plan.stop_loss);
  const risk = entry - stop;
  if (!(risk > 0)) return null;
  const target = cents(entry + minReward * risk, "up");
  if (!isValidLongPlan(entry, target, stop)) return null;
  return {
    ...plan,
    target_price: target.toFixed(2),
    reward_ratio: Math.round(((target - entry) / risk) * 100) / 100,
  };
}
