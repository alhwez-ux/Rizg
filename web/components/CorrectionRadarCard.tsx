"use client";

import { useMemo, useState } from "react";

import { CompanyName } from "@/components/CompanyName";
import { DataSkeleton } from "@/components/DataSkeleton";
import { useCorrectionRadar } from "@/hooks/useCorrectionRadar";
import { ar } from "@/lib/ar";
import { type CorrectionKind, type CorrectionRadarRow } from "@/lib/correctionRadar";
import { formatPrice } from "@/lib/liquidity";
import { passesShariahFilter, type ShariahFilter } from "@/lib/shariah";

type FilterKind = CorrectionKind | "all";

const BADGE_TONE: Record<CorrectionKind, string> = {
  approach: "border-orange-400/50 bg-orange-500/15 text-orange-100",
  rebound: "border-emerald-400/50 bg-emerald-500/15 text-emerald-100",
};

function AlertBadge({ row }: { row: CorrectionRadarRow }) {
  const label = row.signal_kind === "approach" ? ar.correctionApproach : ar.correctionRebound;
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold leading-5 ${BADGE_TONE[row.signal_kind]}`}>
      {label}
    </span>
  );
}

export function CorrectionRadarCard({
  shariahFilter = "all",
  onOpenSymbol,
}: {
  shariahFilter?: ShariahFilter;
  onOpenSymbol?: (company: { symbol: string; name: string }) => void;
}) {
  const { payload, rows, loading, error, late } = useCorrectionRadar();
  const [filter, setFilter] = useState<FilterKind>("all");
  const visible = useMemo(
    () =>
      rows.filter((row) => passesShariahFilter(row.symbol, shariahFilter) && (filter === "all" || row.signal_kind === filter)),
    [filter, rows, shariahFilter],
  );

  return (
    <section className="rounded-2xl border border-orange-500/20 bg-tape-panel/90 p-5 text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 border-b border-zinc-800 pb-4 text-center">
        <h2 className="text-xl font-bold text-zinc-50">{ar.correctionTitle}</h2>
        <p className="mx-auto mt-1 max-w-2xl text-xs leading-relaxed text-zinc-400">{payload?.hint || ar.correctionHint}</p>
        {payload ? (
          <p className="mt-2 text-[11px] text-zinc-500">
            {payload.approach_count} {ar.correctionFilterApproach} · {payload.rebound_count} {ar.correctionFilterRebound}
          </p>
        ) : null}
      </div>

      {error && rows.length === 0 ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : loading && rows.length === 0 ? (
        <DataSkeleton kind="table" rows={5} />
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-center text-sm text-zinc-500">{ar.correctionEmpty}</p>
      ) : (
        <>
          {late ? <p className="mb-3 text-center text-xs text-zinc-500">{ar.liveTicksUpdating}</p> : null}
          <div className="mb-4 flex flex-wrap items-center justify-center gap-2">
            {(
              [
                ["all", ar.correctionFilterAll],
                ["approach", ar.correctionFilterApproach],
                ["rebound", ar.correctionFilterRebound],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setFilter(id)}
                className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                  filter === id
                    ? "border-orange-400/50 bg-orange-500/15 text-orange-100"
                    : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {visible.length === 0 ? (
            <p className="py-8 text-center text-sm text-zinc-500">{ar.correctionEmpty}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-start">
                <thead>
                  <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                    <th className="p-3 font-medium">{ar.correctionColCompany}</th>
                    <th className="p-3 font-medium">{ar.correctionColPrice}</th>
                    <th className="p-3 font-medium">{ar.correctionColAlert}</th>
                    <th className="p-3 font-medium">{ar.correctionColReasons}</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => (
                    <tr key={row.symbol} className="border-b border-zinc-800/80 align-top">
                      <td className="p-3">
                        <button
                          type="button"
                          onClick={() => onOpenSymbol?.({ symbol: row.symbol, name: row.name })}
                          className="text-start"
                        >
                          <CompanyName symbol={row.symbol} name={row.name} align="start" />
                        </button>
                      </td>
                      <td className="p-3 font-mono text-sm tabular-nums text-zinc-100" dir="ltr">
                        {formatPrice(row.last_price)}
                      </td>
                      <td className="p-3">
                        <AlertBadge row={row} />
                      </td>
                      <td className="p-3 text-xs leading-5 text-zinc-400">{row.reasons.join(" · ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
