export interface CashDividend {
  announcementDate: string;
  eligibilityDate: string;
  distributionDate: string;
  amountPerShare: number;
}

const NEAR_ELIGIBILITY_DAYS = 14;

function startOfDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

export function toIsoDate(value: Date | string): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString();
}

export function daysUntil(iso: string, from = new Date()): number | null {
  const target = new Date(iso);
  if (Number.isNaN(target.getTime())) return null;
  const diff = startOfDay(target).getTime() - startOfDay(from).getTime();
  return Math.round(diff / 86_400_000);
}

export function isEligibilityNear(dividend: CashDividend | null | undefined, from = new Date()): boolean {
  if (!dividend) return false;
  const days = daysUntil(dividend.eligibilityDate, from);
  return days != null && days >= 0 && days <= NEAR_ELIGIBILITY_DAYS;
}

export function pickNextDividend(dividends: CashDividend[], from = new Date()): CashDividend | null {
  const upcoming = dividends
    .map((item) => ({ item, days: daysUntil(item.eligibilityDate, from) }))
    .filter((entry) => entry.days != null)
    .sort((a, b) => (a.days ?? 0) - (b.days ?? 0));
  const future = upcoming.find((entry) => (entry.days ?? 0) >= -2);
  return (future ?? upcoming[upcoming.length - 1])?.item ?? null;
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
