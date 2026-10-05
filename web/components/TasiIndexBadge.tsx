"use client";

import { useTasiIndex } from "@/hooks/useTasiIndex";
import { ar } from "@/lib/ar";
import { formatPercent } from "@/lib/liquidity";
import { toneFromChange } from "@/lib/market-tone";

export function TasiIndexBadge() {
  const { quote, status } = useTasiIndex();
  const tone = toneFromChange(quote.change ?? quote.changePercent);
  const live = status === "live";
  const toneClass =
    tone === "up"
      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
      : tone === "down"
        ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
        : "border-zinc-700 bg-zinc-950 text-zinc-200";

  return (
    <div
      className={`inline-flex min-h-11 items-center gap-3 rounded-xl border px-3 py-1.5 ${toneClass}`}
      title={ar.tasiIndexHint}
    >
      <span className="flex items-center gap-1.5 text-xs font-black tracking-wide">
        <span className={`h-2 w-2 rounded-full ${live ? "animate-pulse bg-emerald-400" : "bg-zinc-500"}`} />
        {ar.tasiIndex}
      </span>
      <span className="font-mono text-sm font-bold" dir="ltr">
        {quote.value == null ? "—" : quote.value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
      <span className="flex flex-col items-end font-mono text-[11px] leading-4" dir="ltr">
        <span>{signedPoints(quote.change)}</span>
        <span>{formatPercent(quote.changePercent, 2)}</span>
      </span>
    </div>
  );
}

function signedPoints(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
