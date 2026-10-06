"use client";

import { FinancialGradeBadge } from "@/components/GradeBadge";

export function CompanyStrengthLine({ symbol }: { symbol: string }) {
  return <FinancialGradeBadge symbol={symbol} />;
}
