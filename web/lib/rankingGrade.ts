import { type FinancialGrade } from "@/lib/compliance/grading";

export type { FinancialGrade };
export const FINANCIAL_GRADES: FinancialGrade[] = ["A", "B", "C", "D", "E"];

export const MATRIX_HOLD_MS = 60_000;

const GRADE_RANK: Record<FinancialGrade, number> = { A: 0, B: 1, C: 2, D: 3, E: 4 };

export interface GradeInput {
  symbol?: string | null;
  matrix_score?: number | null;
  net_income?: number | null;
  category?: string | null;
  rating?: string | null;
  grade?: string | null;
  financial_grade?: string | null;
  profit_growth?: number | null;
  debt_ratio?: number | null;
  accumulated_loss_ratio?: number | null;
  last_price?: number | null;
  volume?: number | null;
}

/** A profitable company is never E. E is only an announced net loss or accumulated losses at or above 50% of capital. */
export function financialGrade(row: GradeInput): FinancialGrade | null {
  if (!hasFinancialRank(row)) return null;
  if (isLosingCompany(row)) return "E";
  const health = finite(row.matrix_score) || healthFromCategory(String(row.category || ""));
  const debt = finite(row.debt_ratio);
  const growth = finite(row.profit_growth);
  const highDebt = debt != null && debt >= 0.45;
  const lowDebt = debt == null || debt <= 0.25;
  const excellent = growth == null ? (health != null && health > 80) : growth >= 8;
  const positive = growth == null || growth > 0;
  const pressured = growth != null && growth < 0;
  if (highDebt) return "D";
  if (health != null && health > 80 && lowDebt && excellent && positive) return "A";
  if (health != null && health >= 65 && positive && !pressured) return "B";
  if (health != null && health >= 50) return "C";
  return "D";
}

export function compareByFinancialGrade(left: GradeInput, right: GradeInput): number {
  const leftRank = rankOf(financialGrade(left));
  const rightRank = rankOf(financialGrade(right));
  if (leftRank !== rightRank) return leftRank - rightRank;
  return (finite(right.matrix_score) ?? -1) - (finite(left.matrix_score) ?? -1);
}

function rankOf(grade: FinancialGrade | null): number {
  return grade == null ? FINANCIAL_GRADES.length : GRADE_RANK[grade];
}

function finite(value: number | null | undefined): number | null {
  return value != null && Number.isFinite(value) && value !== 0 ? value : null;
}

function healthFromCategory(category: string): number | null {
  if (category.includes("قلاع")) return 85;
  if (category.includes("واعدة")) return 68;
  if (category.includes("متوسط")) return 55;
  if (category.includes("ضعيف")) return 40;
  return null;
}

function hasFinancialRank(row: GradeInput): boolean {
  const category = String(row.category || "");
  if (/خاسر|قلاع|واعدة|متوسط|ضعيف/.test(category)) return true;
  const score = Number(row.matrix_score);
  return Number.isFinite(score) && score !== 0;
}

function isLosingCompany(row: GradeInput): boolean {
  const income = row.net_income;
  if (income != null && Number.isFinite(income)) return income < 0;
  const accumulated = row.accumulated_loss_ratio;
  return accumulated != null && Number.isFinite(accumulated) && accumulated >= 0.5;
}

/** Use a ready A–E field when the feed has one. Otherwise keep the financial rules. */
export function readyGrade(row: GradeInput): FinancialGrade | null {
  if (isLosingCompany(row)) return "E";
  return (
    letterGrade(row.financial_grade) ||
    letterGrade(row.rating) ||
    letterGrade(row.grade) ||
    letterGrade(row.category) ||
    financialGrade(row)
  );
}

/**
 * Every row gets one grade. A declared loss stays E.
 * Names with no financial list are banded by measured session value: leaders A/B, middle C, smaller names D.
 */
export function classifyRankingRows<T extends GradeInput>(rows: T[]): Array<T & { financial_grade: FinancialGrade }> {
  const grades: Array<FinancialGrade | null> = rows.map((row) => readyGrade(row));
  const pending = grades
    .map((grade, index) => (grade == null ? index : -1))
    .filter((index) => index >= 0)
    .sort((left, right) => sessionValue(rows[right]) - sessionValue(rows[left]) || symbolOf(rows[left]).localeCompare(symbolOf(rows[right])));
  pending.forEach((index, order) => {
    grades[index] = sizeBand(order, pending.length);
  });
  return rows.map((row, index) => ({ ...row, financial_grade: grades[index] ?? "D" }));
}

export function sessionValue(row: GradeInput): number {
  const price = Number(row.last_price);
  const volume = Number(row.volume);
  if (!Number.isFinite(price) || !Number.isFinite(volume) || price <= 0 || volume <= 0) return 0;
  return price * volume;
}

function sizeBand(order: number, count: number): FinancialGrade {
  if (count <= 1) return "A";
  const pct = order / count;
  if (pct < 0.12) return "A";
  if (pct < 0.32) return "B";
  if (pct < 0.62) return "C";
  return "D";
}

function letterGrade(value: string | null | undefined): FinancialGrade | null {
  const text = String(value || "").trim().toUpperCase();
  if (text === "A" || text === "B" || text === "C" || text === "D" || text === "E") return text;
  const embedded = text.match(/(?:فئة|GRADE|RATING)\s*([A-E])/);
  return embedded ? (embedded[1] as FinancialGrade) : null;
}

function symbolOf(row: GradeInput): string {
  return String(row.symbol || "");
}
