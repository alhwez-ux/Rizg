"use client";

import { useState } from "react";

import { fetchRecoveryPlan, type RecoveryPlanResponse } from "@/lib/recovery";

export function useRecoveryPlan() {
  const [payload, setPayload] = useState<RecoveryPlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function calculate(input: { symbol: string; quantity: number; avg_price: number }) {
    setLoading(true);
    setError(null);
    try {
      const next = await fetchRecoveryPlan(input);
      setPayload(next);
      return next;
    } catch (err) {
      const message = err instanceof Error ? err.message : "تعذر حساب خطة التعديل";
      setError(message);
      setPayload(null);
      throw err;
    } finally {
      setLoading(false);
    }
  }

  return { payload, error, loading, calculate, setPayload };
}
