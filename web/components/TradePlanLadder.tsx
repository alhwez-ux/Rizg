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
    <div className="min-h-[52px] rounded-xl border border-zinc-800 bg-zinc-950/70 px-2 py-2 text-center">
      <p className="text-[11px] text-zinc-500">{label}</p>
      <p dir="ltr" className={`mt-0.5 font-mono text-sm font-semibold tabular-nums sm:text-base ${tone}`}>
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
}: {
  entry: number | string | null | undefined;
  stop: number | string | null | undefined;
  resistances?: Array<number | null | undefined>;
  className?: string;
}) {
  const plan = graduatedTargets(entry, stop, resistances);
  if (!plan) return null;
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
