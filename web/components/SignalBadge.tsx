"use client";

import { ar } from "@/lib/ar";
import { formatPrice } from "@/lib/liquidity";
import { signalKind, type ScreenerRow } from "@/lib/screener";

export function SignalBadge({ row }: { row: ScreenerRow }) {
  const kind = signalKind(row);
  if (kind === "entry") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/40 bg-emerald-500/15 px-2.5 py-1 text-xs font-semibold text-emerald-300 shadow-[0_0_18px_rgba(16,185,129,0.25)]">
        {ar.entryBadge}
      </span>
    );
  }
  if (kind === "exit") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/40 bg-amber-500/15 px-2.5 py-1 text-xs font-semibold text-amber-200 shadow-[0_0_18px_rgba(245,158,11,0.2)]">
        {ar.exitBadge}
      </span>
    );
  }
  return (
    <span className="inline-flex rounded-full border border-zinc-800 bg-zinc-900/80 px-2.5 py-1 text-xs text-zinc-500">
      {ar.waitingFlow}
    </span>
  );
}

export function SuggestedPrices({ row }: { row: ScreenerRow }) {
  if (row.entry_signal && row.suggested_entry != null) {
    return (
      <div className="mt-3 space-y-1.5">
        <p className="text-sm font-semibold text-emerald-300">
          {ar.entryPriceLabel}:{" "}
          <span dir="ltr" className="font-mono">
            {formatPrice(row.suggested_entry)}
          </span>
        </p>
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400">
          <span>
            {ar.target}:{" "}
            <span dir="ltr" className="font-mono text-emerald-400">
              {formatPrice(row.target_price)}
            </span>
          </span>
          <span>
            {ar.stopLoss}:{" "}
            <span dir="ltr" className="font-mono text-rose-400">
              {formatPrice(row.stop_loss)}
            </span>
          </span>
        </p>
      </div>
    );
  }
  if (row.exit_signal && row.suggested_exit != null) {
    return (
      <p className="mt-3 text-sm font-semibold text-amber-200">
        {ar.exitPriceLabel}:{" "}
        <span dir="ltr" className="font-mono">
          {formatPrice(row.suggested_exit)}
        </span>
      </p>
    );
  }
  return null;
}
