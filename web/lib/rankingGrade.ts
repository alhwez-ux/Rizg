import { type FinancialGrade } from "@/lib/compliance/grading";
import { TASI_COMPLIANCE_UNIVERSE } from "@/prisma/tasiUniverse";

export type { FinancialGrade };
export const FINANCIAL_GRADES: FinancialGrade[] = ["A", "B", "C", "D", "E"];

export const MATRIX_HOLD_MS = 60_000;

const GRADE_RANK: Record<FinancialGrade, number> = { A: 0, B: 1, C: 2, D: 3, E: 4 };
const DEBT_BY_SYMBOL = new Map(TASI_COMPLIANCE_UNIVERSE.map((item) => [item.symbol, item.debtRatio]));

export interface GradeInput {
  symbol?: string | null;
  matrix_score?: number | null;
  net_income?: number | null;
  category?: string | null;
  profit_growth?: number | null;
  debt_ratio?: number | null;
}

/** Losing companies are E. Health above 80 with low debt and strong operating returns is A. */
export function financialGrade(row: GradeInput): FinancialGrade | null {
  if (!hasFinancialRank(row)) return null;
  if (isLosingCompany(row)) return "E";
  const health = finite(row.matrix_score);
  const debt = finite(row.debt_ratio) ?? debtFor(row.symbol);
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
  return value != null && Number.isFinite(value) ? value : null;
}

function debtFor(symbol: string | null | undefined): number | null {
  const key = String(symbol || "").trim().toUpperCase();
  if (!key) return null;
  const debt = DEBT_BY_SYMBOL.get(key);
  return debt == null ? null : debt;
}

function hasFinancialRank(row: GradeInput): boolean {
  const category = String(row.category || "");
  if (/خاسر|قلاع|واعدة|متوسط|ضعيف/.test(category)) return true;
  const score = Number(row.matrix_score);
  return Number.isFinite(score) && score !== 0;
}

function isLosingCompany(row: GradeInput): boolean {
  if (String(row.category || "").includes("خاسر")) return true;
  if (row.net_income != null && Number.isFinite(row.net_income) && row.net_income <= 0) return true;
  const score = Number(row.matrix_score);
  return Number.isFinite(score) && score < 0;
}
