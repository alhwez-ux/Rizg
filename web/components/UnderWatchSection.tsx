"use client";

import { ar } from "@/lib/ar";
import { formatMoney, formatPercent, formatPrice, formatVolume } from "@/lib/liquidity";
import { displayCompanyTitle } from "@/lib/listedCompanies";
import { EXPLOSIVE_WATCH_FLAG, type UnderWatchRow } from "@/lib/underWatch";

export function UnderWatchSection({
  rows,
  loading,
  onOpen,
}: {
  rows: UnderWatchRow[];
  loading?: boolean;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  return (
    <section className="rounded-2xl border border-amber-500/25 bg-gradient-to-b from-amber-500/10 to-tape-panel/90 p-5 text-center shadow-[0_0_36px_rgba(245,158,11,0.08)] sm:p-6">
      <div className="mb-4 flex flex-col items-center gap-2">
        <p className="flex items-center justify-center gap-2 text-xl font-bold text-zinc-50">
          <WatchPulse explosive={rows.some((row) => row.explosive)} />
          {ar.underWatchTitle}
        </p>
        <p className="text-xs text-zinc-400">{ar.underWatchHint}</p>
      </div>

      {loading && rows.length === 0 ? (
        <p className="py-8 text-sm text-zinc-500">{ar.liveRadarLoading}</p>
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-8 text-sm text-zinc-500">
          {ar.underWatchEmpty}
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {rows.map((row) => (
            <UnderWatchCard key={row.symbol} row={row} onOpen={onOpen} />
          ))}
        </div>
      )}
    </section>
  );
}

export function UnderWatchBanner({
  count,
  onOpen,
}: {
  count: number;
  onOpen?: () => void;
}) {
  if (count <= 0) return null;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center justify-center gap-2 rounded-2xl border border-amber-400/40 bg-amber-500/10 px-4 py-3 text-sm font-semibold text-amber-100 shadow-[0_0_24px_rgba(245,158,11,0.12)] transition hover:border-amber-300 hover:bg-amber-500/20"
    >
      <span className="inline-flex animate-rocketPulse text-lg" aria-hidden="true">
        🚀
      </span>
      {ar.underWatchTitle}
      <span className="rounded-full bg-amber-400/20 px-2 py-0.5 font-mono text-xs text-amber-50">{count}</span>
    </button>
  );
}

function UnderWatchCard({
  row,
  onOpen,
}: {
  row: UnderWatchRow;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  const title = displayCompanyTitle(row.symbol, row.name);
  const explosive = row.explosive || row.flag === EXPLOSIVE_WATCH_FLAG;
  return (
    <article
      className={`rounded-2xl border p-4 text-start ${
        explosive
          ? "border-amber-400/50 bg-amber-500/10 shadow-[0_0_22px_rgba(245,158,11,0.16)]"
          : "border-sky-500/30 bg-sky-500/5"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={() => onOpen?.({ symbol: row.symbol, name: title || row.name || row.symbol })}
          className="min-w-0 text-start"
        >
          <p className="flex items-center gap-2 font-mono text-lg font-semibold text-zinc-50">
            <WatchPulse explosive={explosive} />
            {row.symbol}
          </p>
          {title ? <p className="mt-0.5 truncate text-xs text-zinc-400">{title}</p> : null}
        </button>
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
            explosive
              ? "border-amber-400/50 bg-amber-500/20 text-amber-100"
              : "border-sky-400/40 bg-sky-500/15 text-sky-100"
          }`}
        >
          {explosive ? ar.underWatchExplosive : ar.underWatchFlag}
        </span>
      </div>

      <div className="mt-3 flex items-baseline justify-between gap-3">
        <p dir="ltr" className="font-mono text-xl text-zinc-100">
          {formatPrice(row.price)}
        </p>
        <p
          dir="ltr"
          className={`text-sm ${(row.change_percent ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}
        >
          {formatPercent(row.change_percent)}
        </p>
      </div>

      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-zinc-400">
        <span>
          {ar.netFlow}{" "}
          <span dir="ltr" className="font-mono text-zinc-200">
            {formatMoney(row.net_flow ?? 0)}
          </span>
        </span>
        {row.volume_ratio != null ? (
          <span>
            {ar.underWatchVolume}{" "}
            <span dir="ltr" className="font-mono text-amber-200">
              {row.volume_ratio.toFixed(1)}×
            </span>
          </span>
        ) : null}
        {row.volume != null ? (
          <span>
            {formatVolume(row.volume)}
          </span>
        ) : null}
      </p>

      {row.reasons[1] ? (
        <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-zinc-400">{row.reasons[1]}</p>
      ) : null}

      {onOpen ? (
        <button
          type="button"
          onClick={() => onOpen({ symbol: row.symbol, name: title || row.name || row.symbol })}
          className="mt-3 w-full rounded-xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 transition hover:border-amber-400 hover:text-amber-100"
        >
          {ar.underWatchOpen}
        </button>
      ) : null}
    </article>
  );
}

export function WatchPulse({ explosive = false }: { explosive?: boolean }) {
  return (
    <span
      className={explosive ? "inline-flex animate-rocketPulse text-base" : "inline-flex animate-lightningPulse text-base"}
      aria-hidden="true"
    >
      {explosive ? "🚀" : "⚡"}
    </span>
  );
}
