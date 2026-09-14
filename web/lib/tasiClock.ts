/** TASI session clock (Asia/Riyadh). Matches backend `app.services.tasi_clock`. */

const RIYADH_OFFSET_MS = 3 * 60 * 60 * 1000;

export type TasiPhase = "weekend" | "closed" | "preopen" | "open" | "auction";

const PHASE_LABEL: Record<TasiPhase, string> = {
  weekend: "عطلة تاسي",
  closed: "السوق مغلق",
  preopen: "تجهيز الافتتاح",
  open: "جلسة تداول",
  auction: "مزاد الإغلاق",
};

export function nowRiyadh(moment: Date = new Date()): Date {
  return new Date(moment.getTime() + RIYADH_OFFSET_MS);
}

export function tasiSessionPhase(moment: Date = new Date()): TasiPhase {
  const riyadh = nowRiyadh(moment);
  const weekday = riyadh.getUTCDay();
  if (weekday === 5 || weekday === 6) return "weekend";
  const minutes = riyadh.getUTCHours() * 60 + riyadh.getUTCMinutes();
  if (minutes < 9 * 60 + 30) return "closed";
  if (minutes < 10 * 60) return "preopen";
  if (minutes <= 15 * 60) return "open";
  if (minutes < 15 * 60 + 30) return "auction";
  return "closed";
}

export function isTasiLiveSession(moment: Date = new Date()): boolean {
  return tasiSessionPhase(moment) === "open";
}

export function tasiPhaseLabel(phase: TasiPhase): string {
  return PHASE_LABEL[phase];
}

export function recommendationButtonLabel(live: boolean): "توصيات لحظية" | "توصيات الإغلاق" {
  return live ? "توصيات لحظية" : "توصيات الإغلاق";
}
