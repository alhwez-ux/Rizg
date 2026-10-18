"use client";

import { DataSkeleton } from "@/components/DataSkeleton";
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

function rangeText(low: string, high: string): string {
  if (!low) return "—";
  if (!high || low === high) return low;
  return `${low} – ${high}`;
}

function houseLine(count: number): string {
  if (count === 1) return "📊 سجّلها محلل بارز واحد";
  if (count === 2) return "📊 أجمع عليها محللان بارزان";
  return `📊 أجمع عليها ${count} محللين بارزين`;
}

function ConsensusCard({
  row,
  onOpen,
}: {
  row: AnalystPickRow;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  const exit = row.direction === "exit";
  const tone = exit ? "border-rose-400/35" : "border-emerald-400/30";
  const chip = exit ? "border-rose-400/30 bg-rose-500/10 text-rose-100" : "border-emerald-400/30 bg-emerald-500/10 text-emerald-100";
  return (
    <article className={`rounded-2xl border bg-zinc-950/50 p-4 text-start ${tone}`}>
      <button type="button" onClick={() => onOpen?.({ symbol: row.symbol, name: row.name })} className="w-full text-start">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <span className="min-w-0">
            <span className="block font-bold text-zinc-50">{row.name}</span>
            <span className="mt-0.5 block font-mono text-xs text-zinc-400" dir="ltr">
              {row.symbol}
            </span>
          </span>
          <span className={`rounded-full border px-2.5 py-1 text-[11px] font-bold ${chip}`}>
            {exit ? ar.analystExitBadge : ar.analystEntryBadge}
          </span>
        </div>
        <p className={`mt-3 text-sm font-semibold ${exit ? "text-rose-50" : "text-emerald-50"}`}>{houseLine(row.analyst_count || row.houses.length)}</p>
        <p className="mt-1 text-[11px] text-zinc-500">{ar.analystConsensusWindow}</p>
        <div className="mt-3 flex min-h-[28px] flex-wrap gap-1.5">
          {row.houses.map((house) => (
            <span key={house} className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${chip}`}>
              {house}
            </span>
          ))}
        </div>
        <p className="mt-3 text-sm leading-relaxed text-zinc-200">{row.note || ar.analystReasonMissing}</p>
        <p className="mt-3 font-mono text-[11px] tabular-nums text-zinc-300" dir="ltr">
          {ar.analystConsensusPrice} {row.last_price != null ? row.last_price.toFixed(2) : "—"}
        </p>
        <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
          <div className="min-h-[52px] rounded-xl border border-zinc-800 px-2 py-2">
            <dt className="text-[11px] text-zinc-500">{exit ? "سعر التخارج" : ar.analystConsensusEntry}</dt>
            <dd dir="ltr" className="font-mono text-sm font-semibold tabular-nums text-zinc-100">
              {rangeText(row.entry_low || row.entry_price, row.entry_high || row.entry_price)}
            </dd>
          </div>
          <div className="min-h-[52px] rounded-xl border border-zinc-800 px-2 py-2">
            <dt className="text-[11px] text-zinc-500">{ar.analystConsensusTarget}</dt>
            <dd dir="ltr" className="font-mono text-sm font-semibold tabular-nums text-emerald-300">
              {rangeText(row.target_low || row.target_price, row.target_high || row.target_price)}
            </dd>
          </div>
          <div className="min-h-[52px] rounded-xl border border-zinc-800 px-2 py-2">
            <dt className="text-[11px] text-zinc-500">{ar.analystConsensusStop}</dt>
            <dd dir="ltr" className="font-mono text-sm font-semibold tabular-nums text-rose-300">
              {rangeText(row.stop_low || row.stop_loss, row.stop_high || row.stop_loss)}
            </dd>
          </div>
        </dl>
        {row.shariah_label ? <p className="mt-3 text-[11px] text-emerald-200/80">{row.shariah_label}</p> : null}
        {row.analyst_count >= 2 && !exit ? (
          <p className="mt-3 text-[11px] font-bold text-amber-100">{ar.analystConsensusBadge}</p>
        ) : null}
      </button>
    </article>
  );
}

function ConsensusList({
  title,
  rows,
  empty,
  onOpen,
}: {
  title: string;
  rows: AnalystPickRow[];
  empty: string;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  return (
    <div>
      <h3 className="mb-3 text-start text-base font-bold text-zinc-100">{title}</h3>
      {rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-8 text-sm text-zinc-500">{empty}</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {rows.map((row) => (
            <ConsensusCard key={`${row.direction}-${row.symbol}`} row={row} onOpen={onOpen} />
          ))}
        </div>
      )}
    </div>
  );
}

export function AnalystConsensusCard({
  payload,
  loading,
  error,
  onOpenSymbol,
  mode = "book",
}: {
  payload: AnalystConsensusResponse | null;
  loading?: boolean;
  error?: string | null;
  onOpenSymbol?: (company: { symbol: string; name: string }) => void;
  mode?: "book" | "window";
}) {
  const rows = payload?.data ?? [];
  const exits = payload?.exits ?? [];
  if (mode === "window") {
    return (
      <section className="rounded-2xl border border-amber-400/25 bg-tape-panel/90 p-5 text-center text-zinc-100 shadow-glow sm:p-6">
        <div className="mb-5 border-b border-zinc-800 pb-4">
          <h2 className="text-xl font-bold text-zinc-50">{ar.tabsConsensus}</h2>
          <p className="mx-auto mt-1 max-w-2xl text-xs leading-relaxed text-zinc-400">{ar.analystConsensusHint}</p>
        </div>
        {error ? (
          <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
        ) : loading && rows.length === 0 && exits.length === 0 ? (
          <DataSkeleton kind="grid" rows={2} />
        ) : (
          <div className="space-y-8">
            <ConsensusList title={ar.analystBuyTitle} rows={rows} empty={ar.analystConsensusEmpty} onOpen={onOpenSymbol} />
            <ConsensusList title={ar.analystExitTitle} rows={exits} empty={ar.analystExitEmpty} onOpen={onOpenSymbol} />
          </div>
        )}
        <p className="mt-4 text-xs leading-relaxed text-zinc-500">{payload?.hint || ar.analystDisclaimer}</p>
      </section>
    );
  }
  return (
    <section className="rounded-2xl border border-violet-400/20 bg-tape-panel/90 p-5 text-center text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 border-b border-zinc-800 pb-4">
        <h2 className="text-xl font-bold text-zinc-50">{ar.analystTitle}</h2>
        <p className="mx-auto mt-1 max-w-2xl text-xs leading-relaxed text-zinc-400">{ar.analystHint}</p>
      </div>
      {error ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : loading && rows.length === 0 ? (
        <DataSkeleton kind="grid" rows={2} />
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
