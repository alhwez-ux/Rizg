"use client";

import { ar } from "@/lib/ar";
import type { ScreenerRow } from "@/lib/screener";
import { formatPrice } from "@/lib/liquidity";

export interface SignalToastItem {
  id: string;
  row: ScreenerRow;
}

export function SignalToasts({
  toasts,
  onDismiss,
}: {
  toasts: SignalToastItem[];
  onDismiss: (id: string) => void;
}) {
  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-50 flex flex-col items-center gap-2 px-3 sm:items-end sm:px-6">
      {toasts.map((toast) => {
        const entry = toast.row.entry_signal;
        return (
          <button
            key={toast.id}
            type="button"
            onClick={() => onDismiss(toast.id)}
            className={`pointer-events-auto w-full max-w-md animate-toastIn rounded-2xl border px-4 py-3 text-start shadow-glow ${
              entry
                ? "border-emerald-400/50 bg-emerald-950/90 text-emerald-50"
                : "border-amber-400/50 bg-amber-950/90 text-amber-50"
            }`}
          >
            <p className="text-sm font-semibold">
              {entry ? ar.entryBadge : ar.exitBadge} · {toast.row.symbol}
              {toast.row.name ? ` — ${toast.row.name}` : ""}
            </p>
            <p className="mt-1 text-sm">
              {entry
                ? `${ar.entryPriceLabel}: ${formatPrice(toast.row.suggested_entry)}`
                : `${ar.exitPriceLabel}: ${formatPrice(toast.row.suggested_exit)}`}
            </p>
            {entry ? (
              <p className="mt-1 text-xs text-emerald-200/80">
                {ar.target} {formatPrice(toast.row.target_price)} · {ar.stopLoss}{" "}
                {formatPrice(toast.row.stop_loss)}
              </p>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
