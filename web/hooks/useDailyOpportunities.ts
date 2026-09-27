"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useConnectionGuard } from "@/hooks/useConnectionGuard";
import { fetchDailyOpportunities, type DailyOpportunitiesResponse, type DailyOpportunityRow } from "@/lib/dailyOpportunities";
import { rememberClientLock } from "@/lib/entryLock";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";

const POLL_MS = 15_000;

export function useDailyOpportunities(pureOnly: boolean) {
  const [payload, setPayload] = useState<DailyOpportunitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  const { isConnected } = useConnectionGuard();

  const refresh = useCallback(async () => {
    try {
      const next = await fetchDailyOpportunities(pureOnly);
      if (!alive.current) return;
      setPayload({ ...next, data: next.data.map((row) => holdEntry(row)) });
      setError(null);
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error ? err.message : "تعذر جلب فرص رزق اليومية");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [pureOnly]);

  useEffect(() => {
    if (!isConnected) {
      setLoading(false);
      return;
    }
    alive.current = true;
    setLoading(true);
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, POLL_MS);
    const onRefresh = () => {
      void refresh();
    };
    window.addEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
      window.removeEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    };
  }, [isConnected, refresh]);

  return { payload, rows: payload?.data ?? [], loading, error, refresh };
}

function holdEntry(row: DailyOpportunityRow): DailyOpportunityRow {
  const locked = rememberClientLock("daily", row.symbol, {
    entry_price: row.entry_price,
    target_price: row.target_price,
    stop_loss: row.stop_loss,
    reward_ratio: row.reward_ratio,
  });
  return { ...row, ...locked };
}
