"use client";

import { useTasiCorrection } from "@/hooks/useTasiCorrection";
import { useTasiIndex } from "@/hooks/useTasiIndex";
import { ar } from "@/lib/ar";
import { formatPercent } from "@/lib/liquidity";
import { toneFromChange } from "@/lib/market-tone";
import { correctionLamp, type TasiCorrectionState } from "@/lib/tasiCorrection";

const LAMP_LABEL: Record<TasiCorrectionState, string> = {
  safe: ar.tasiLampSafe,
  approach: ar.tasiLampApproach,
  confirmed: ar.tasiLampConfirmed,
  ending: ar.tasiLampEnding,
  rebound: ar.tasiLampRebound,
};

export function TasiIndexBadge() {
  const { quote } = useTasiIndex();
  const correction = useTasiCorrection();
  const lamp = correctionLamp(correction?.state);
  const tone = toneFromChange(quote.change ?? quote.changePercent);
  const state = correction?.state ?? null;
  const stateLabel = state ? LAMP_LABEL[state] : "";
  const numberTone =
    tone === "up" ? "text-emerald-300" : tone === "down" ? "text-rose-300" : "text-zinc-200";
  const shell =
    lamp === "danger"
      ? "border-rose-500/80 bg-rose-950/70 text-rose-50"
      : lamp === "warn"
        ? "border-amber-500/80 bg-amber-950/60 text-amber-50"
        : "border-zinc-700 bg-zinc-950 text-zinc-100";
  const reasons = correction?.reasons?.filter(Boolean).join(" · ") ?? "";
  const reading =
    quote.value == null
      ? "—"
      : quote.value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div
      className={`inline-flex min-h-11 items-center gap-2 rounded-full border px-3 py-1 ${shell}`}
      data-tasi-lamp={lamp}
      title={reasons ? `${ar.tasiIndexHint} — ${stateLabel}: ${reasons}` : ar.tasiIndexHint}
      aria-label={stateLabel ? `${ar.tasiIndex} ${reading} ${stateLabel}` : `${ar.tasiIndex} ${reading}`}
    >
      <span className="flex items-center gap-1.5 text-xs font-black tracking-wide">
        <CorrectionLed lamp={lamp} />
        {ar.tasiIndex}
      </span>
      <span className={`font-mono text-sm font-bold ${numberTone}`} dir="ltr">
        {reading}
      </span>
      <span className={`font-mono text-[11px] ${numberTone}`} dir="ltr">
        {signedPoints(quote.change)}
        <span className="ms-1">{formatPercent(quote.changePercent, 2)}</span>
      </span>
      {stateLabel ? <span className="text-[11px] font-bold">{stateLabel}</span> : null}
    </div>
  );
}

function CorrectionLed({ lamp }: { lamp: ReturnType<typeof correctionLamp> }) {
  if (lamp === "danger" || lamp === "warn") {
    const color = lamp === "danger" ? "bg-rose-500" : "bg-amber-500";
    const glow =
      lamp === "danger"
        ? "shadow-[0_0_12px_3px_rgba(244,63,94,0.95)]"
        : "shadow-[0_0_12px_3px_rgba(245,158,11,0.95)]";
    return (
      <span className="relative inline-flex h-3.5 w-3.5 shrink-0" aria-hidden="true">
        <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${color}`} />
        <span className={`relative inline-flex h-3.5 w-3.5 animate-pulse rounded-full ${color} ${glow}`} />
      </span>
    );
  }
  if (lamp === "calm") {
    return <span className="inline-flex h-3.5 w-3.5 shrink-0 rounded-full bg-emerald-400" aria-hidden="true" />;
  }
  if (lamp === "settle") {
    return <span className="inline-flex h-3.5 w-3.5 shrink-0 rounded-full bg-amber-400" aria-hidden="true" />;
  }
  return <span className="inline-flex h-3.5 w-3.5 shrink-0 rounded-full bg-zinc-600" aria-hidden="true" />;
}

function signedPoints(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
