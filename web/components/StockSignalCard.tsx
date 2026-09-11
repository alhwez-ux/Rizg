"use client";

import { SignalBadge, SuggestedPrices } from "@/components/SignalBadge";
import { ar } from "@/lib/ar";
import { formatMoney, formatPercent, formatPrice, formatRatio } from "@/lib/liquidity";
import { type ScreenerRow } from "@/lib/screener";

export function StockSignalCard({
  row,
  selected,
  onSelect,
  onRemove,
}: {
  row: ScreenerRow;
  selected?: boolean;
  onSelect?: (symbol: string) => void;
  onRemove?: (symbol: string) => void;
}) {
  const positive = row.net_flow > 0;
  const negative = row.net_flow < 0;

  return (
    <article
      className={`rounded-2xl border p-4 transition ${
        row.entry_signal
          ? "border-emerald-500/40 bg-emerald-500/5"
          : row.exit_signal
            ? "border-amber-500/40 bg-amber-500/5"
            : "border-zinc-800/80 bg-tape-panel"
      } ${selected ? "ring-1 ring-emerald-400/60" : ""}`}
    >
      <div className="flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={() => onSelect?.(row.symbol)}
          className="min-w-0 text-start"
        >
          <p className="font-mono text-lg font-semibold text-zinc-50">{row.symbol}</p>
          {row.name ? <p className="truncate text-xs text-zinc-500">{row.name}</p> : null}
        </button>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <SignalBadge row={row} />
          {onRemove ? (
            <button
              type="button"
              onClick={() => onRemove(row.symbol)}
              className="text-xs text-zinc-500 hover:text-rose-300"
            >
              {ar.remove}
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-3 flex items-baseline justify-between gap-3">
        <p dir="ltr" className="font-mono text-xl text-zinc-100">
          {formatPrice(row.price || null)}
        </p>
        <p
          dir="ltr"
          className={`text-sm ${row.change_percent >= 0 ? "text-emerald-400" : "text-rose-400"}`}
        >
          {formatPercent(row.change_percent)}
        </p>
      </div>

      <p
        className={`mt-2 text-sm ${positive ? "text-emerald-400" : negative ? "text-rose-400" : "text-zinc-400"}`}
      >
        {ar.netFlow}{" "}
        <span dir="ltr" className="font-mono">
          {formatMoney(row.net_flow)}
        </span>
      </p>

      <SuggestedPrices row={row} />

      <p className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-500">
        <span>
          {ar.vwap} <span dir="ltr">{formatPrice(row.vwap)}</span>
        </span>
        <span>
          {ar.atr} <span dir="ltr">{formatPrice(row.atr)}</span>
        </span>
        <span>
          {ar.bookPressure} {formatRatio(row.book_pressure)}
        </span>
      </p>
    </article>
  );
}
