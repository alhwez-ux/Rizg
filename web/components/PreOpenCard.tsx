"use client";

import { useMemo, useState } from "react";

import { ar } from "@/lib/ar";
import { formatMoney, formatPercent, formatPrice, formatVolume } from "@/lib/liquidity";
import { buySharePercent, type PreOpenRow, type PreOpenScanResponse, type PreOpenSignalKind } from "@/lib/preopen";
import { passesShariahFilter, type ShariahFilter } from "@/lib/shariah";

type FilterKind = PreOpenSignalKind | "all";

const SIGNAL_TONE: Record<PreOpenSignalKind, string> = {
  accumulation: "border-emerald-400/40 bg-emerald-500/15 text-emerald-200 shadow-[0_0_16px_rgba(16,185,129,0.18)]",
  distribution: "border-rose-400/40 bg-rose-500/15 text-rose-200 shadow-[0_0_16px_rgba(244,63,94,0.18)]",
  balanced: "border-zinc-600/40 bg-zinc-800/60 text-zinc-300",
};

const SIGNAL_LABEL: Record<PreOpenSignalKind, string> = {
  accumulation: ar.preopenAccumulation,
  distribution: ar.preopenDistribution,
  balanced: ar.preopenBalanced,
};

const STATE_LABEL: Record<PreOpenRow["liquidity_state"], string> = {
  تجميع: ar.preopenLiquidityAccum,
  تصريف: ar.preopenLiquidityDist,
  توازن: ar.preopenLiquidityBalanced,
};

function blockLabel(row: PreOpenRow): string | null {
  if (row.large_block_side === "buy") return ar.preopenBlocksBuy;
  if (row.large_block_side === "sell") return ar.preopenBlocksSell;
  if (row.large_block_side === "mixed") return ar.preopenBlocksMixed;
  if (row.block_trades > 0) return ar.preopenBlocksMixed;
  return null;
}

function BookBar({ row }: { row: PreOpenRow }) {
  const buyPct = buySharePercent(row);
  const sellPct = 100 - buyPct;
  const empty = row.buy_volume <= 0 && row.sell_volume <= 0;
  return (
    <div className="min-w-[160px]">
      <div className="flex h-2.5 overflow-hidden rounded-full bg-zinc-800" dir="ltr">
        <span className="h-full bg-emerald-400/90" style={{ width: `${empty ? 50 : buyPct}%` }} />
        <span className="h-full bg-rose-400/90" style={{ width: `${empty ? 50 : sellPct}%` }} />
      </div>
      <p className="mt-1.5 flex flex-wrap items-center justify-center gap-x-3 gap-y-0.5 font-mono text-[11px]" dir="ltr">
        <span className="text-emerald-300">
          {ar.preopenBuy} {row.buy_volume ? formatVolume(row.buy_volume) : "—"}
        </span>
        <span className="text-rose-300">
          {ar.preopenSell} {row.sell_volume ? formatVolume(row.sell_volume) : "—"}
        </span>
      </p>
    </div>
  );
}

function LiquidityBadge({ row }: { row: PreOpenRow }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs font-bold ${SIGNAL_TONE[row.signal_kind]}`}>
      <span aria-hidden="true">{row.signal_kind === "accumulation" ? "▲" : row.signal_kind === "distribution" ? "▼" : "◆"}</span>
      {row.signal || SIGNAL_LABEL[row.signal_kind]}
      <span className="font-medium opacity-80">· {STATE_LABEL[row.liquidity_state]}</span>
    </span>
  );
}

function PreOpenRowCard({
  row,
  onOpen,
}: {
  row: PreOpenRow;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  const blocks = blockLabel(row);
  return (
    <button
      type="button"
      onClick={() => onOpen?.({ symbol: row.symbol, name: row.name })}
      className="w-full rounded-2xl border border-zinc-800 bg-zinc-950/50 p-4 text-center transition hover:border-amber-500/30 hover:bg-zinc-950/80"
    >
      <div className="flex flex-wrap items-center justify-center gap-2">
        <span className="font-bold text-zinc-50">{row.name}</span>
        <span className="font-mono text-xs text-zinc-400" dir="ltr">
          {row.symbol}
        </span>
      </div>
      <div className="mt-3">
        <LiquidityBadge row={row} />
      </div>
      <p className="mt-3 font-mono text-lg font-semibold text-amber-100" dir="ltr">
        {formatPrice(row.expected_open)}
        <span
          className={`ms-2 text-sm ${
            (row.open_variation_pct ?? 0) > 0
              ? "text-emerald-300"
              : (row.open_variation_pct ?? 0) < 0
                ? "text-rose-300"
                : "text-zinc-400"
          }`}
        >
          {formatPercent(row.open_variation_pct)}
        </span>
      </p>
      <div className="mt-3">
        <BookBar row={row} />
      </div>
      {blocks ? (
        <p className="mt-2 text-[11px] text-amber-200/90">
          {blocks}
          {row.last_block_value ? (
            <span className="ms-1 font-mono" dir="ltr">
              {formatMoney(row.last_block_value)}
            </span>
          ) : null}
        </p>
      ) : null}
    </button>
  );
}

export function PreOpenCard({
  payload,
  loading,
  error,
  shariahFilter = "all",
  onOpenSymbol,
}: {
  payload: PreOpenScanResponse | null;
  loading?: boolean;
  error?: string | null;
  shariahFilter?: ShariahFilter;
  onOpenSymbol?: (company: { symbol: string; name: string }) => void;
}) {
  const [filter, setFilter] = useState<FilterKind>("all");
  const rows = payload?.data ?? [];
  const visible = useMemo(
    () =>
      rows
        .filter((row) => (filter === "all" ? true : row.signal_kind === filter))
        .filter((row) => passesShariahFilter(row.symbol, shariahFilter)),
    [filter, rows, shariahFilter],
  );

  return (
    <section className="rounded-2xl border border-amber-500/20 bg-tape-panel/90 p-5 text-center text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 flex flex-col items-center gap-3 border-b border-zinc-800 pb-4">
        <div>
          <h2 className="text-xl font-bold text-zinc-50">{ar.preopenTitle}</h2>
          <p className="mt-1 text-xs text-zinc-400">{ar.preopenHint}</p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <span
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-bold ${
              payload?.in_window
                ? "border-amber-400/50 bg-amber-500/20 text-amber-100"
                : "border-zinc-700 bg-zinc-900 text-zinc-400"
            }`}
          >
            {payload?.in_window ? (
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-300 opacity-70" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-300" />
              </span>
            ) : null}
            {payload?.in_window ? ar.preopenLive : ar.preopenIdle}
            <span className="font-mono font-medium" dir="ltr">
              {ar.preopenWindow}
            </span>
          </span>
          {payload && payload.count > 0 ? (
            <span className="text-xs text-zinc-500">
              {payload.accumulation_count} {ar.preopenAccumulation} · {payload.distribution_count} {ar.preopenDistribution}
            </span>
          ) : null}
        </div>
      </div>

      {error ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : loading && rows.length === 0 ? (
        <p className="py-10 text-sm text-zinc-500">{ar.preopenLoading}</p>
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-sm text-zinc-500">{ar.preopenEmpty}</p>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-center gap-2">
            {(
              [
                ["all", ar.preopenFilterAll],
                ["accumulation", ar.preopenAccumulation],
                ["distribution", ar.preopenDistribution],
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
                          ? "border-emerald-400/50 bg-emerald-500/20 text-emerald-100"
                          : "border-amber-400/50 bg-amber-500/20 text-amber-100"
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
                  <PreOpenRowCard key={row.symbol} row={row} onOpen={onOpenSymbol} />
                ))}
              </div>

              <div className="hidden overflow-x-auto lg:block">
                <table className="w-full min-w-[860px] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                      <th className="p-3 text-center font-medium">{ar.preopenColCompany}</th>
                      <th className="p-3 text-center font-medium">{ar.preopenColSymbol}</th>
                      <th className="p-3 text-center font-medium">{ar.preopenColExpected}</th>
                      <th className="p-3 text-center font-medium">{ar.preopenColBook}</th>
                      <th className="p-3 text-center font-medium">{ar.preopenColState}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {visible.map((row) => {
                      const blocks = blockLabel(row);
                      return (
                        <tr
                          key={row.symbol}
                          className="cursor-pointer transition-colors hover:bg-zinc-950/40"
                          onClick={() => onOpenSymbol?.({ symbol: row.symbol, name: row.name })}
                        >
                          <td className="p-3 text-center">
                            <span className="font-bold text-zinc-50">{row.name}</span>
                            {row.sector ? <p className="mt-0.5 text-[11px] text-zinc-500">{row.sector}</p> : null}
                          </td>
                          <td className="p-3 text-center font-mono text-zinc-200" dir="ltr">
                            {row.symbol}
                          </td>
                          <td className="p-3 text-center">
                            <span className="inline-block font-mono text-base font-semibold text-amber-100" dir="ltr">
                              {formatPrice(row.expected_open)}
                            </span>
                            <p
                              className={`mt-0.5 font-mono text-xs ${
                                (row.open_variation_pct ?? 0) > 0
                                  ? "text-emerald-300"
                                  : (row.open_variation_pct ?? 0) < 0
                                    ? "text-rose-300"
                                    : "text-zinc-400"
                              }`}
                              dir="ltr"
                            >
                              {formatPercent(row.open_variation_pct)}
                            </p>
                          </td>
                          <td className="p-3 text-center">
                            <BookBar row={row} />
                            {blocks ? (
                              <p className="mt-1 text-[11px] text-amber-200/80">
                                {blocks}
                                {row.last_block_value ? (
                                  <span className="ms-1 font-mono" dir="ltr">
                                    {formatMoney(row.last_block_value)}
                                  </span>
                                ) : null}
                              </p>
                            ) : null}
                          </td>
                          <td className="p-3 text-center">
                            <LiquidityBadge row={row} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      <p className="mt-4 text-xs leading-relaxed text-zinc-500">{payload?.hint || ar.preopenHint}</p>
    </section>
  );
}

export default PreOpenCard;
