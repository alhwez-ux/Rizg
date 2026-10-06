import { ar } from "@/lib/ar";
import { graduatedTargets } from "@/lib/tradeTargets";

function money(value: number | string | null | undefined): string {
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number) || number <= 0) return "—";
  return number.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function Cell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 px-1.5 py-1.5 text-center">
      <p className="text-[10px] leading-4 text-zinc-500">{label}</p>
      <p dir="ltr" className={`mt-0.5 font-mono text-xs font-semibold tabular-nums sm:text-sm ${tone}`}>
        {value}
      </p>
    </div>
  );
}

export function TradePlanLadder({
  entry,
  stop,
  resistances,
  className,
  variant = "stack",
}: {
  entry: number | string | null | undefined;
  stop: number | string | null | undefined;
  resistances?: Array<number | null | undefined>;
  className?: string;
  variant?: "stack" | "row";
}) {
  const plan = graduatedTargets(entry, stop, resistances);
  if (!plan) return null;
  if (variant === "row") {
    return (
      <div className={className}>
        <p className="mb-1 text-[10px] text-zinc-500">
          {ar.dailyEntry} <span dir="ltr" className="font-mono text-zinc-300">{money(entry)}</span>
        </p>
        <div className="grid grid-cols-4 gap-1.5">
          <Cell label={ar.target1} value={money(plan.t1)} tone="text-emerald-200" />
          <Cell label={ar.target2} value={money(plan.t2)} tone="text-emerald-300" />
          <Cell label={ar.target3} value={money(plan.t3)} tone="text-emerald-400" />
          <Cell label={ar.stopLoss} value={money(stop)} tone="text-rose-300" />
        </div>
      </div>
    );
  }
  return (
    <div className={`grid gap-2 ${className ?? ""}`}>
      <div className="grid grid-cols-2 gap-2">
        <Cell label={ar.dailyEntry} value={money(entry)} tone="text-zinc-100" />
        <Cell label={ar.dailyStop} value={money(stop)} tone="text-rose-300" />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Cell label={`${ar.target1} · 1:1`} value={money(plan.t1)} tone="text-emerald-200" />
        <Cell label={`${ar.target2} · 1:2`} value={money(plan.t2)} tone="text-emerald-300" />
        <Cell label={`${ar.target3} · 1:3`} value={money(plan.t3)} tone="text-emerald-400" />
      </div>
    </div>
  );
}
