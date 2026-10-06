"use client";

import { useEffect, useState } from "react";

import { ar } from "@/lib/ar";
import { companyRankFor } from "@/lib/rankingMatrix";
import { financialGrade, type FinancialGrade } from "@/lib/rankingGrade";

const LABEL: Record<FinancialGrade, string> = {
  A: ar.rankingGradeA,
  B: ar.rankingGradeB,
  C: ar.rankingGradeC,
  D: ar.rankingGradeD,
  E: ar.rankingGradeE,
};

export function gradeBadgeClass(grade: FinancialGrade): string {
  if (grade === "A" || grade === "B") return "border-emerald-400/40 bg-emerald-500/15 text-emerald-200";
  if (grade === "C") return "border-amber-400/40 bg-amber-500/15 text-amber-200";
  return "border-rose-400/40 bg-rose-500/15 text-rose-200";
}

export function GradeBadge({ grade }: { grade: FinancialGrade | null | undefined }) {
  if (!grade) return null;
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-bold ${gradeBadgeClass(grade)}`}>
      {LABEL[grade]}
    </span>
  );
}

export function FinancialGradeBadge({ symbol }: { symbol: string }) {
  const [grade, setGrade] = useState<FinancialGrade | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    companyRankFor(symbol)
      .then((row) => {
        if (alive) setGrade(row ? financialGrade(row) : null);
      })
      .catch(() => {
        if (alive) setGrade(null);
      });
    return () => {
      alive = false;
    };
  }, [symbol]);

  if (!grade) return null;
  return <GradeBadge grade={grade} />;
}
