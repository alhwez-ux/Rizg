"use client";

import { useMemo } from "react";

import { StockRadarTable } from "@/components/StockRadarTable";
import { useScreener } from "@/hooks/useScreener";
import { useStockRadar } from "@/hooks/useStockRadar";
import { type ScreenerRow } from "@/lib/screener";

export function StockRadarView({
  selectedSymbol,
  onSelect,
  screenerRows,
}: {
  selectedSymbol?: string;
  onSelect?: (symbol: string) => void;
  screenerRows?: ScreenerRow[];
}) {
  const { rows, loading, error, refresh } = useStockRadar();
  const { snapshot } = useScreener();
  const liveRows = useMemo(() => {
    if (screenerRows?.length) return screenerRows;
    const combined = [...(snapshot?.watchlist ?? []), ...(snapshot?.radar ?? [])];
    return combined.filter(
      (row, index, items) => items.findIndex((item) => item.symbol === row.symbol) === index,
    );
  }, [screenerRows, snapshot]);

  return (
    <StockRadarTable
      rows={rows}
      loading={loading}
      error={error}
      onRetry={() => {
        void refresh();
      }}
      selectedSymbol={selectedSymbol}
      onSelect={onSelect}
      screenerRows={liveRows}
    />
  );
}
