import { nowRiyadh, tasiSessionPhase } from "@/lib/tasiClock";

/** Live session poll. Inside the 3–5 second window requested for the open. */
export const OPEN_POLL_MS = 4_000;

const PREOPEN_MINUTE = 9 * 60 + 30;

/** Shorten the wait while TASI is in pre-open, the session, or the closing auction. */
export function sessionPollMs(idleMs: number, moment: Date = new Date()): number {
  const phase = tasiSessionPhase(moment);
  if (phase === "preopen" || phase === "open" || phase === "auction") {
    return Math.min(idleMs, OPEN_POLL_MS);
  }
  const riyadh = nowRiyadh(moment);
  const weekday = riyadh.getUTCDay();
  if (weekday === 5 || weekday === 6) return idleMs;
  const minutes = riyadh.getUTCHours() * 60 + riyadh.getUTCMinutes();
  if (minutes >= PREOPEN_MINUTE) return idleMs;
  const untilPreopen = (PREOPEN_MINUTE - minutes) * 60_000 - riyadh.getUTCSeconds() * 1000;
  return Math.max(1_000, Math.min(idleMs, untilPreopen));
}
