"use client";

import { StockRadarTable } from "@/components/StockRadarTable";
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
      screenerRows={screenerRows}
    />
  );
}
