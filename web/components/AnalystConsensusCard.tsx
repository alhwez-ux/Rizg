"use client";

import { ar } from "@/lib/ar";
import type { AnalystConsensusResponse, AnalystPickRow } from "@/lib/analystConsensus";
import { isValidLongPlan } from "@/lib/tradeGeometry";

function PickCard({
  row,
  onOpen,
}: {
  row: AnalystPickRow;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  if (!isValidLongPlan(row.entry_price, row.target_price, row.stop_loss)) return null;
  return (
    <article className="min-h-[210px] rounded-2xl border border-violet-400/25 bg-zinc-950/50 p-4 text-start">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <button type="button" onClick={() => onOpen?.({ symbol: row.symbol, name: row.name })} className="min-w-0 text-start">
          <p className="font-bold text-zinc-50">{row.name}</p>
          <p className="mt-0.5 font-mono text-xs text-zinc-400" dir="ltr">
            {row.symbol}
          </p>
        </button>
        <div className="text-end">
          <p className="text-[11px] text-zinc-500">{ar.analystTimeframe}</p>
          <p className="text-sm font-semibold text-violet-100">{row.timeframe}</p>
        </div>
      </div>
      <div className="mt-3 flex min-h-[28px] flex-wrap gap-1.5">
        {row.houses.map((house) => (
          <span key={house} className="rounded-full border border-violet-400/30 bg-violet-500/10 px-2.5 py-1 text-[11px] font-semibold text-violet-100">
            {house}
          </span>
        ))}
      </div>
      <p className="mt-3 min-h-[18px] font-mono text-[11px] tabular-nums text-zinc-400" dir="ltr">
        {ar.dailyLast} {row.last_price != null ? row.last_price.toFixed(2) : "—"}
      </p>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div className="min-h-[52px] rounded-xl border border-zinc-800 px-2 py-2">
          <dt className="text-[11px] text-zinc-500">{ar.dailyEntry}</dt>
          <dd dir="ltr" className="font-mono text-sm font-semibold tabular-nums text-zinc-100">
            {row.entry_price}
          </dd>
        </div>
        <div className="min-h-[52px] rounded-xl border border-zinc-800 px-2 py-2">
          <dt className="text-[11px] text-zinc-500">{ar.dailyTarget}</dt>
          <dd dir="ltr" className="font-mono text-sm font-semibold tabular-nums text-emerald-300">
            {row.target_price}
          </dd>
        </div>
        <div className="min-h-[52px] rounded-xl border border-zinc-800 px-2 py-2">
          <dt className="text-[11px] text-zinc-500">{ar.dailyStop}</dt>
          <dd dir="ltr" className="font-mono text-sm font-semibold tabular-nums text-rose-300">
            {row.stop_loss}
          </dd>
        </div>
      </dl>
      <p className="mt-3 min-h-[18px] text-[11px] text-zinc-500">
        {row.shariah_label ? <span className="me-2 text-emerald-200/80">{row.shariah_label}</span> : null}
        <span dir="ltr" className="font-mono tabular-nums">
          1:{row.reward_ratio.toFixed(1)}
        </span>
        {row.note ? <span className="ms-2">{row.note}</span> : null}
      </p>
    </article>
  );
}

export function AnalystConsensusCard({
  payload,
  loading,
  error,
  onOpenSymbol,
}: {
  payload: AnalystConsensusResponse | null;
  loading?: boolean;
  error?: string | null;
  onOpenSymbol?: (company: { symbol: string; name: string }) => void;
}) {
  const rows = payload?.data ?? [];
  return (
    <section className="rounded-2xl border border-violet-400/20 bg-tape-panel/90 p-5 text-center text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 border-b border-zinc-800 pb-4">
        <h2 className="text-xl font-bold text-zinc-50">{ar.analystTitle}</h2>
        <p className="mx-auto mt-1 max-w-2xl text-xs leading-relaxed text-zinc-400">{ar.analystHint}</p>
      </div>
      {error ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : loading && rows.length === 0 ? (
        <p className="py-10 text-sm text-zinc-500">{ar.analystLoading}</p>
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-sm text-zinc-500">{ar.analystEmpty}</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {rows.map((row) => (
            <PickCard key={row.symbol} row={row} onOpen={onOpenSymbol} />
          ))}
        </div>
      )}
      <p className="mt-4 text-xs leading-relaxed text-zinc-500">{payload?.hint || ar.analystDisclaimer}</p>
    </section>
  );
}
