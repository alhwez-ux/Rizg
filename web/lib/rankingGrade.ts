import { gradeFromScore, type FinancialGrade } from "@/lib/compliance/grading";

export type { FinancialGrade };
export const FINANCIAL_GRADES: FinancialGrade[] = ["A", "B", "C", "D", "E"];

export const MATRIX_HOLD_MS = 60_000;

export interface GradeInput {
  matrix_score?: number | null;
  net_income?: number | null;
  category?: string | null;
}

/** Losing companies are E. Stronger profitable scores occupy A, then B, then C, then D. */
export function financialGrade(row: GradeInput): FinancialGrade | null {
  if (!hasFinancialRank(row)) return null;
  if (isLosingCompany(row)) return "E";
  const letter = gradeFromScore(Number(row.matrix_score));
  return letter === "E" ? "D" : letter;
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
