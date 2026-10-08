"use client";

import { useMemo } from "react";

import { CompanyName } from "@/components/CompanyName";
import { FinancialGradeBadge } from "@/components/GradeBadge";
import { DataSkeleton } from "@/components/DataSkeleton";
import { PathBadge } from "@/components/PathBadge";
import { ar } from "@/lib/ar";
import { formatMoney, formatPercent, formatPrice, formatVolume } from "@/lib/liquidity";
import { buySharePercent, type PreOpenRow, type PreOpenScanResponse, type PreOpenSignalKind } from "@/lib/preopen";
import { passesShariahFilter, type ShariahFilter } from "@/lib/shariah";

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
        <span className="inline-flex flex-col items-center gap-1">
          <CompanyName symbol={row.symbol} name={row.name} />
          <FinancialGradeBadge symbol={row.symbol} />
        </span>
        <PathBadge price={row.expected_open} change={row.open_variation_pct} />
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

function PreOpenBoard({
  title,
  rows,
  tone,
  onOpen,
}: {
  title: string;
  rows: PreOpenRow[];
  tone: string;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  return (
    <div className={`rounded-2xl border p-3 text-start ${tone}`}>
      <div className="mb-3 flex min-h-8 items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-zinc-50">{title}</h3>
        <span className="rounded-full bg-zinc-950/70 px-2 py-0.5 font-mono text-xs tabular-nums text-zinc-300">{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-3 py-8 text-center text-xs text-zinc-500">{ar.preopenEmpty}</p>
      ) : (
        <div className="grid gap-3">
          {rows.map((row) => (
            <PreOpenRowCard key={row.symbol} row={row} onOpen={onOpen} />
          ))}
        </div>
      )}
    </div>
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
  const rows = payload?.data ?? [];
  const visible = useMemo(
    () => rows.filter((row) => passesShariahFilter(row.symbol, shariahFilter)),
    [rows, shariahFilter],
  );
  const accumulation = visible.filter((row) => row.signal_kind === "accumulation");
  const distribution = visible.filter((row) => row.signal_kind === "distribution");
  const balanced = visible.filter((row) => row.signal_kind === "balanced");

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

      {error && rows.length === 0 ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : loading && rows.length === 0 ? (
        <DataSkeleton kind="table" rows={4} />
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-sm text-zinc-500">{ar.preopenEmpty}</p>
      ) : (
        <>
          {error ? <p className="mb-3 text-center text-xs text-zinc-500">{ar.liveTicksUpdating}</p> : null}
          {visible.length === 0 ? (
            <p className="text-sm text-zinc-500">{ar.shariahFilterEmpty}</p>
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <PreOpenBoard
                title={ar.preopenAccumulation}
                rows={accumulation}
                tone="border-emerald-500/30 bg-emerald-500/5"
                onOpen={onOpenSymbol}
              />
              <PreOpenBoard
                title={ar.preopenDistribution}
                rows={distribution}
                tone="border-rose-500/30 bg-rose-500/5"
                onOpen={onOpenSymbol}
              />
              {balanced.length > 0 ? (
                <div className="lg:col-span-2">
                  <PreOpenBoard
                    title={ar.preopenBalanced}
                    rows={balanced}
                    tone="border-zinc-700 bg-zinc-950/40"
                    onOpen={onOpenSymbol}
                  />
                </div>
              ) : null}
            </div>
          )}
        </>
      )}

      <p className="mt-4 text-xs leading-relaxed text-zinc-500">{payload?.hint || ar.preopenHint}</p>
    </section>
  );
}

export default PreOpenCard;
