export interface CashDividend {
  announcementDate: string;
  eligibilityDate: string;
  distributionDate: string;
  amountPerShare: number;
}

const NEAR_ELIGIBILITY_DAYS = 14;

function riyadhDay(from: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Riyadh",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(from);
}

function eligibilityDay(iso: string): string {
  const trimmed = iso.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return trimmed;
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return "";
  return riyadhDay(parsed);
}

export function toIsoDate(value: Date | string): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString();
}

export function daysUntil(iso: string, from = new Date()): number | null {
  const target = eligibilityDay(iso);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(target)) return null;
  const today = riyadhDay(from);
  const start = Date.parse(`${today}T00:00:00Z`);
  const end = Date.parse(`${target}T00:00:00Z`);
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return Math.round((end - start) / 86_400_000);
}

export function isEligibilityNear(dividend: CashDividend | null | undefined, from = new Date()): boolean {
  if (!dividend) return false;
  const days = daysUntil(dividend.eligibilityDate, from);
  return days != null && days >= 0 && days <= NEAR_ELIGIBILITY_DAYS;
}

export function pickNextDividend(dividends: CashDividend[], from = new Date()): CashDividend | null {
  const upcoming = dividends
    .map((item) => ({ item, days: daysUntil(item.eligibilityDate, from) }))
    .filter((entry) => entry.days != null && entry.days >= 0)
    .sort((a, b) => (a.days ?? 0) - (b.days ?? 0));
  return upcoming[0]?.item ?? null;
}

export function serializeDividend(input: {
  announcementDate: Date;
  eligibilityDate: Date;
  distributionDate: Date;
  amountPerShare: number;
}): CashDividend {
  return {
    announcementDate: toIsoDate(input.announcementDate),
    eligibilityDate: toIsoDate(input.eligibilityDate),
    distributionDate: toIsoDate(input.distributionDate),
    amountPerShare: input.amountPerShare,
  };
}
