"use client";

import { DataSkeleton } from "@/components/DataSkeleton";
import { ar } from "@/lib/ar";
import type { DailyOpportunitiesResponse, DailyOpportunityRow } from "@/lib/dailyOpportunities";
import { isValidLongPlan } from "@/lib/tradeGeometry";

function Level({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="min-h-[52px] rounded-xl border border-zinc-800 bg-zinc-950/70 px-3 py-2">
      <p className="text-[11px] text-zinc-500">{label}</p>
      <p dir="ltr" className={`mt-0.5 font-mono text-base font-semibold tabular-nums ${tone}`}>
        {value}
      </p>
    </div>
  );
}

function OpportunityCard({
  row,
  onOpen,
}: {
  row: DailyOpportunityRow;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  if (!isValidLongPlan(row.entry_price, row.target_price, row.stop_loss)) return null;
  return (
    <article className="flex min-h-[220px] flex-col rounded-2xl border border-sky-500/25 bg-zinc-950/50 p-4 text-start">
      <div className="flex items-start justify-between gap-3">
        <button type="button" onClick={() => onOpen?.({ symbol: row.symbol, name: row.name })} className="min-w-0 text-start">
          <p className="truncate font-bold text-zinc-50">{row.name}</p>
          <p className="mt-0.5 font-mono text-xs text-zinc-400" dir="ltr">
            {row.symbol}
            {row.sector ? <span className="ms-2 font-sans text-zinc-500">{row.sector}</span> : null}
          </p>
        </button>
        <span className="shrink-0 rounded-full border border-emerald-400/40 bg-emerald-500/15 px-2.5 py-1 font-mono text-xs font-bold text-emerald-100 tabular-nums" dir="ltr">
          1:{row.reward_ratio.toFixed(1)}
        </span>
      </div>
      <p className="mt-2 min-h-[18px] text-[11px] text-sky-200/90">{row.setup}</p>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Level label={ar.dailyEntry} value={row.entry_price} tone="text-zinc-100" />
        <Level label={ar.dailyTarget} value={row.target_price} tone="text-emerald-300" />
        <Level label={ar.dailyStop} value={row.stop_loss} tone="text-rose-300" />
      </div>
      <p className="mt-3 min-h-[32px] text-[11px] leading-relaxed text-zinc-400">
        {ar.dailyLast}{" "}
        <span dir="ltr" className="inline-block min-w-[4.5rem] font-mono tabular-nums text-zinc-200">
          {row.last_price != null ? row.last_price.toFixed(2) : "—"}
        </span>
        <span className="mx-1 text-zinc-600">·</span>
        {row.timeframe}
        {row.shariah_label ? (
          <>
            <span className="mx-1 text-zinc-600">·</span>
            {row.shariah_label}
          </>
        ) : null}
      </p>
      {row.reason ? <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-zinc-500">{row.reason}</p> : null}
    </article>
  );
}

export function DailyOpportunitiesCard({
  payload,
  loading,
  error,
  onOpenSymbol,
}: {
  payload: DailyOpportunitiesResponse | null;
  loading?: boolean;
  error?: string | null;
  onOpenSymbol?: (company: { symbol: string; name: string }) => void;
}) {
  const rows = payload?.data ?? [];
  return (
    <section className="rounded-2xl border border-sky-500/20 bg-tape-panel/90 p-5 text-center text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 border-b border-zinc-800 pb-4">
        <h2 className="text-xl font-bold text-zinc-50">{ar.dailyTitle}</h2>
        <p className="mx-auto mt-1 max-w-2xl text-xs leading-relaxed text-zinc-400">{ar.dailyHint}</p>
        <p className="mt-2 min-h-4 text-[11px] text-zinc-500">{payload?.session_label || "\u00a0"}</p>
      </div>
      {error ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : loading && rows.length === 0 ? (
        <DataSkeleton kind="grid" rows={2} />
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-sm text-zinc-500">{ar.dailyEmpty}</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 text-start md:grid-cols-2">
          {rows.map((row) => (
            <OpportunityCard key={row.symbol} row={row} onOpen={onOpenSymbol} />
          ))}
        </div>
      )}
      <p className="mt-4 text-xs leading-relaxed text-zinc-500">{payload?.hint || ar.dailyHint}</p>
    </section>
  );
}
