export type FinancialGrade = "A" | "B" | "C" | "D" | "E";

export const GRADE_ORDER: FinancialGrade[] = ["A", "B", "C", "D", "E"];

export interface GradeBreakdown {
  solvency: number;
  dividends: number;
  valuation: number;
  growth: number;
  total: number;
  grade: FinancialGrade;
}

function clamp(value: number, min = 0, max = 100): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

/** Lower leverage and a healthier current ratio raise the solvency pillar. */
export function scoreSolvency(debtRatio: number, currentRatio: number): number {
  const debtScore = clamp(100 - debtRatio * 150);
  const liquidityScore = clamp(currentRatio * 42);
  return clamp(0.65 * debtScore + 0.35 * liquidityScore);
}

/** Yield, payout continuity, and a live cash dividend all feed this pillar. */
export function scoreDividends(dividendYield: number, consecutiveYears: number, amountPerShare: number): number {
  const yieldScore = clamp(dividendYield * 1800);
  const historyScore = clamp(consecutiveYears * 14);
  const cashScore = amountPerShare > 0 ? 78 : 18;
  return clamp(0.5 * yieldScore + 0.3 * historyScore + 0.2 * cashScore);
}

/** Mid-teens P/E and a moderate P/B are treated as the attractive band. */
export function scoreValuation(peRatio: number, pbRatio: number): number {
  const peScore = peRatio <= 0 ? 20 : clamp(100 - Math.abs(peRatio - 13) * 5.5);
  const pbScore = pbRatio <= 0 ? 20 : clamp(100 - Math.abs(pbRatio - 1.8) * 22);
  return clamp(0.6 * peScore + 0.4 * pbScore);
}

export function scoreGrowth(revenueGrowth: number, operatingGrowth: number): number {
  const revScore = clamp(50 + revenueGrowth * 220);
  const opScore = clamp(50 + operatingGrowth * 240);
  return clamp(0.55 * revScore + 0.45 * opScore);
}

export function gradeFromScore(total: number): FinancialGrade {
  if (total >= 80) return "A";
  if (total >= 65) return "B";
  if (total >= 50) return "C";
  if (total >= 35) return "D";
  return "E";
}

export function gradeCompany(input: {
  debtRatio: number;
  currentRatio: number;
  dividendYield: number;
  consecutiveYears: number;
  amountPerShare: number;
  peRatio: number;
  pbRatio: number;
  revenueGrowth: number;
  operatingGrowth: number;
}): GradeBreakdown {
  const solvency = scoreSolvency(input.debtRatio, input.currentRatio);
  const dividends = scoreDividends(input.dividendYield, input.consecutiveYears, input.amountPerShare);
  const valuation = scoreValuation(input.peRatio, input.pbRatio);
  const growth = scoreGrowth(input.revenueGrowth, input.operatingGrowth);
  const total = clamp(0.3 * solvency + 0.2 * dividends + 0.25 * valuation + 0.25 * growth);
  return { solvency, dividends, valuation, growth, total, grade: gradeFromScore(total) };
}

export function classifyLoss(input: {
  netIncomeMargin: number;
  operatingGrowth: number;
  ema50: number;
  ema200: number;
  rsi: number;
}): { isLosing: boolean; lossReason: string | null } {
  if (input.netIncomeMargin < 0) {
    return { isLosing: true, lossReason: "خسائر تشغيلية في آخر القوائم المالية" };
  }
  if (input.operatingGrowth < -0.08) {
    return { isLosing: true, lossReason: "تراجع حاد في الأرباح الصافية ربعياً / سنوياً" };
  }
  if (input.ema50 < input.ema200 * 0.97 && input.rsi < 45) {
    return { isLosing: true, lossReason: "هبوط فني تحت متوسطات الحركة (EMA 50/200)" };
  }
  return { isLosing: false, lossReason: null };
}
