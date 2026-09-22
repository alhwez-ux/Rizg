"use client";

import { useMemo, useState } from "react";

import { SmartMoneyIcon } from "@/components/SmartMoneyIcon";
import { ar } from "@/lib/ar";
import { formatMoney, formatPrice } from "@/lib/liquidity";
import { type SmartMoneyKind, type SmartMoneyRow, type SmartMoneyScanResponse } from "@/lib/smartMoney";
import { passesShariahFilter, type ShariahFilter } from "@/lib/shariah";

type FilterKind = SmartMoneyKind | "all";

const BADGE_TONE: Record<string, string> = {
  صناديق: "border-indigo-400/50 bg-indigo-500/20 text-indigo-100 shadow-[0_0_16px_rgba(99,102,241,0.28)]",
  "محفظة كبرى": "border-amber-400/50 bg-amber-500/15 text-amber-100 shadow-[0_0_18px_rgba(251,191,36,0.28)]",
  "تصريف مؤسسي": "border-rose-400/40 bg-rose-500/15 text-rose-200",
  مراقبة: "border-zinc-500/40 bg-zinc-800/70 text-zinc-300",
};

function FundBadge({ row }: { row: SmartMoneyRow }) {
  const tone = BADGE_TONE[row.badge] ?? BADGE_TONE.صناديق;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold ${tone}`}>
      <SmartMoneyIcon className="h-3.5 w-3.5 shrink-0" />
      {row.badge || ar.fundsBadgeFunds}
    </span>
  );
}

function FlowMeter({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className="min-w-[120px]">
      <div className="h-2 overflow-hidden rounded-full bg-zinc-800" dir="ltr">
        <span
          className={`block h-full ${pct >= 82 ? "bg-amber-400" : pct >= 62 ? "bg-indigo-400" : "bg-zinc-500"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1 font-mono text-xs text-indigo-100" dir="ltr">
        {pct.toFixed(0)}
      </p>
    </div>
  );
}

function PlanCell({ row }: { row: SmartMoneyRow }) {
  if (!row.plan_ok || row.entry == null || row.target == null || row.stop == null) {
    return <span className="text-xs text-zinc-500">{ar.fundsNoLongPlan}</span>;
  }
  return (
    <div className="font-mono text-xs leading-6" dir="ltr">
      <p className="text-zinc-200">
        {ar.fundsEntry} {formatPrice(row.entry)}
      </p>
      <p className="text-emerald-300">
        {ar.fundsTarget} {formatPrice(row.target)}
      </p>
      <p className="text-rose-300">
        {ar.fundsStop} {formatPrice(row.stop)}
      </p>
    </div>
  );
}

function SmartMoneyRowCard({
  row,
  onOpen,
}: {
  row: SmartMoneyRow;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen?.({ symbol: row.symbol, name: row.name })}
      className="w-full rounded-2xl border border-indigo-500/20 bg-zinc-950/50 p-4 text-center transition hover:border-indigo-400/40 hover:bg-zinc-950/80"
    >
      <div className="flex flex-wrap items-center justify-center gap-2">
        <span className="font-bold text-zinc-50">{row.name}</span>
        <span className="font-mono text-xs text-zinc-400" dir="ltr">
          {row.symbol}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
        <FundBadge row={row} />
        <span className="text-xs text-indigo-200">{row.signal}</span>
      </div>
      <div className="mt-3 flex justify-center">
        <FlowMeter score={row.institutional_flow_score} />
      </div>
      <p className="mt-2 text-[11px] text-zinc-400">
        {ar.fundsVsRetail}: {row.inst_share_pct.toFixed(0)}% / {row.retail_share_pct.toFixed(0)}%
      </p>
      <div className="mt-3">
        <PlanCell row={row} />
      </div>
      {row.reason ? <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">{row.reason}</p> : null}
    </button>
  );
}

export function SmartMoneyCard({
  payload,
  loading,
  error,
  shariahFilter = "all",
  onOpenSymbol,
}: {
  payload: SmartMoneyScanResponse | null;
  loading?: boolean;
  error?: string | null;
  shariahFilter?: ShariahFilter;
  onOpenSymbol?: (company: { symbol: string; name: string }) => void;
}) {
  const [filter, setFilter] = useState<FilterKind>("accumulation");
  const rows = payload?.data ?? [];
  const visible = useMemo(
    () =>
      rows
        .filter((row) => (filter === "all" ? true : row.signal_kind === filter))
        .filter((row) => passesShariahFilter(row.symbol, shariahFilter)),
    [filter, rows, shariahFilter],
  );

  return (
    <section className="rounded-2xl border border-indigo-500/25 bg-tape-panel/90 p-5 text-center text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 flex flex-col items-center gap-3 border-b border-zinc-800 pb-4">
        <div>
          <h2 className="flex items-center justify-center gap-2 text-xl font-bold text-zinc-50">
            <SmartMoneyIcon className="h-6 w-6 text-indigo-300" />
            {ar.fundsTitle}
          </h2>
          <p className="mt-1 text-xs text-zinc-400">{ar.fundsHint}</p>
        </div>
        {payload && payload.count > 0 ? (
          <span className="text-xs text-zinc-500">
            {payload.accumulation_count} {ar.fundsFilterAccum} · {payload.watch_count} {ar.fundsFilterWatch} ·{" "}
            {payload.distribution_count} {ar.fundsFilterDist}
          </span>
        ) : null}
      </div>

      {error ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : loading && rows.length === 0 ? (
        <p className="py-10 text-sm text-zinc-500">{ar.fundsLoading}</p>
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-sm text-zinc-500">{ar.fundsEmpty}</p>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-center gap-2">
            {(
              [
                ["accumulation", ar.fundsFilterAccum],
                ["watch", ar.fundsFilterWatch],
                ["distribution", ar.fundsFilterDist],
                ["all", ar.fundsFilterAll],
              ] as const
            ).map(([id, label]) => {
              const selected = filter === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setFilter(id)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                    selected
                      ? id === "distribution"
                        ? "border-rose-400/50 bg-rose-500/20 text-rose-100"
                        : id === "accumulation"
                          ? "border-indigo-400/50 bg-indigo-500/20 text-indigo-100"
                          : "border-zinc-400/40 bg-zinc-700/40 text-zinc-100"
                      : "border-zinc-700 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>

          {visible.length === 0 ? (
            <p className="text-sm text-zinc-500">{ar.shariahFilterEmpty}</p>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
                {visible.map((row) => (
                  <SmartMoneyRowCard key={row.symbol} row={row} onOpen={onOpenSymbol} />
                ))}
              </div>

              <div className="hidden overflow-x-auto lg:block">
                <table className="w-full min-w-[980px] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                      <th className="p-3 text-center font-medium">{ar.fundsColCompany}</th>
                      <th className="p-3 text-center font-medium">{ar.fundsColBadge}</th>
                      <th className="p-3 text-center font-medium">{ar.fundsColScore}</th>
                      <th className="p-3 text-center font-medium">{ar.fundsColShare}</th>
                      <th className="p-3 text-center font-medium">{ar.fundsColBlocks}</th>
                      <th className="p-3 text-center font-medium">{ar.fundsColPlan}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {visible.map((row) => (
                      <tr
                        key={row.symbol}
                        className="cursor-pointer transition-colors hover:bg-zinc-950/40"
                        onClick={() => onOpenSymbol?.({ symbol: row.symbol, name: row.name })}
                      >
                        <td className="p-3 text-center">
                          <span className="font-bold text-zinc-50">{row.name}</span>
                          <p className="mt-0.5 font-mono text-[11px] text-zinc-400" dir="ltr">
                            {row.symbol}
                          </p>
                          {row.sector ? <p className="text-[11px] text-zinc-500">{row.sector}</p> : null}
                        </td>
                        <td className="p-3 text-center">
                          <FundBadge row={row} />
                          <p className="mt-1 text-[11px] text-indigo-200/80">{row.signal}</p>
                        </td>
                        <td className="p-3 text-center">
                          <FlowMeter score={row.institutional_flow_score} />
                        </td>
                        <td className="p-3 text-center">
                          <p className="font-mono text-xs text-indigo-200" dir="ltr">
                            {row.inst_share_pct.toFixed(0)}% {ar.fundsInstitutions}
                          </p>
                          <p className="font-mono text-[11px] text-zinc-500" dir="ltr">
                            {row.retail_share_pct.toFixed(0)}% {ar.fundsRetail}
                          </p>
                        </td>
                        <td className="p-3 text-center">
                          <p className="font-mono text-zinc-100">{row.block_trades}</p>
                          {row.last_block_value ? (
                            <p className="mt-0.5 font-mono text-[11px] text-amber-200/80" dir="ltr">
                              {formatMoney(row.last_block_value)}
                            </p>
                          ) : null}
                          {row.near_bid_wall ? (
                            <p className="mt-0.5 text-[11px] text-indigo-300">{ar.fundsNearBidWall}</p>
                          ) : null}
                        </td>
                        <td className="p-3 text-center">
                          <PlanCell row={row} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      <p className="mt-4 text-xs leading-relaxed text-zinc-500">{payload?.hint || ar.fundsHint}</p>
    </section>
  );
}

export default SmartMoneyCard;
