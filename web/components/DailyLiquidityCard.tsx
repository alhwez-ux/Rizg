"use client";

import { useEffect, useMemo, useState } from "react";

import { ar } from "@/lib/ar";
import { fetchDailyLiquidity, type DailyLiquidityRow, type LiquidityGrade } from "@/lib/dailyLiquidity";
import { formatMoney, formatPercent, formatPrice, formatVolume } from "@/lib/liquidity";

const GRADE_TONE: Record<LiquidityGrade, string> = {
  A: "border-emerald-400/40 bg-emerald-500/15 text-emerald-200",
  B: "border-sky-400/40 bg-sky-500/15 text-sky-200",
  C: "border-amber-400/40 bg-amber-500/15 text-amber-200",
  D: "border-rose-400/40 bg-rose-500/15 text-rose-200",
};

const GRADE_LABEL: Record<LiquidityGrade, string> = {
  A: ar.flowGradeA,
  B: ar.flowGradeB,
  C: ar.flowGradeC,
  D: ar.flowGradeD,
};

export function DailyLiquidityCard({
  onOpenSymbol,
}: {
  onOpenSymbol?: (company: { symbol: string; name: string }) => void;
}) {
  const [rows, setRows] = useState<DailyLiquidityRow[]>([]);
  const [isRevealed, setIsRevealed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<LiquidityGrade | "all">("all");

  const reveal = async () => {
    if (isRevealed) {
      setIsRevealed(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setRows(await fetchDailyLiquidity());
      setIsRevealed(true);
    } catch {
      setRows([]);
      setError(ar.flowDetectorError);
      setIsRevealed(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isRevealed) return;
    const timer = window.setInterval(() => {
      void fetchDailyLiquidity()
        .then((next) => {
          setRows(next);
          setError(null);
        })
        .catch(() => {
          /* keep last snapshot while TickChart refreshes */
        });
    }, 12_000);
    return () => window.clearInterval(timer);
  }, [isRevealed]);

  const visible = useMemo(
    () => (filter === "all" ? rows : rows.filter((row) => row.grade === filter)),
    [filter, rows],
  );

  return (
    <section className="rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 text-center text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 flex flex-col items-center gap-4 border-b border-zinc-800 pb-4">
        <div>
          <h2 className="text-xl font-bold text-zinc-50">{ar.flowDetectorTitle}</h2>
          <p className="mt-1 text-xs text-zinc-500">{ar.flowDetectorHint}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            void reveal();
          }}
          disabled={loading}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-sky-600 to-teal-600 px-8 py-3 text-sm font-bold text-white shadow-lg shadow-sky-900/30 transition hover:from-sky-500 hover:to-teal-500 disabled:opacity-50"
        >
          {loading ? ar.flowDetectorLoading : isRevealed ? ar.flowDetectorHide : ar.flowDetectorButton}
        </button>
      </div>

      {isRevealed ? (
        <div className="animate-fadeIn">
          {error ? (
            <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {error}
            </p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-zinc-500">{ar.flowDetectorEmpty}</p>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-center justify-center gap-2">
                {(["all", "A", "B", "C", "D"] as const).map((grade) => {
                  const selected = filter === grade;
                  const label = grade === "all" ? ar.flowFilterAll : GRADE_LABEL[grade];
                  return (
                    <button
                      key={grade}
                      type="button"
                      onClick={() => setFilter(grade)}
                      className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                        selected
                          ? "border-sky-400/50 bg-sky-500/20 text-sky-100"
                          : "border-zinc-700 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              <div className="overflow-x-auto text-start">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                      <th className="p-3 text-center font-medium">#</th>
                      <th className="p-3 text-center font-medium">{ar.tableColCompany}</th>
                      <th className="p-3 text-center font-medium">{ar.flowColGrade}</th>
                      <th className="p-3 text-center font-medium">{ar.flowColInflow}</th>
                      <th className="p-3 text-center font-medium">{ar.netFlow}</th>
                      <th className="p-3 text-center font-medium">{ar.lastPrice}</th>
                      <th className="p-3 text-center font-medium">{ar.heatmapColChange}</th>
                      <th className="p-3 text-center font-medium">{ar.rankingColVolume}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60 text-sm">
                    {visible.map((row) => (
                      <tr
                        key={row.symbol}
                        className="cursor-pointer transition-colors hover:bg-zinc-950/40"
                        onClick={() => onOpenSymbol?.({ symbol: row.symbol, name: row.name })}
                      >
                        <td className="p-3 text-center font-mono text-xs text-zinc-500" dir="ltr">
                          {row.rank}
                        </td>
                        <td className="p-3 text-center">
                          <span className="inline-flex flex-wrap items-center justify-center gap-2 font-bold">
                            <span>{row.name}</span>
                            <span className="font-mono text-xs font-normal text-zinc-400" dir="ltr">
                              ({row.symbol})
                            </span>
                          </span>
                        </td>
                        <td className="p-3 text-center">
                          <span
                            className={`inline-block rounded-lg border px-2.5 py-1 text-xs font-bold ${GRADE_TONE[row.grade]}`}
                          >
                            {GRADE_LABEL[row.grade]}
                          </span>
                        </td>
                        <td
                          className={`p-3 text-center font-mono ${row.inflow > 0 ? "text-emerald-300" : "text-zinc-400"}`}
                          dir="ltr"
                        >
                          {formatMoney(row.inflow)}
                        </td>
                        <td
                          className={`p-3 text-center font-mono ${
                            row.net_flow > 0 ? "text-emerald-300" : row.net_flow < 0 ? "text-rose-300" : "text-zinc-300"
                          }`}
                          dir="ltr"
                        >
                          {formatMoney(row.net_flow)}
                        </td>
                        <td className="p-3 text-center font-mono font-semibold text-zinc-100" dir="ltr">
                          {formatPrice(row.last_price)}
                        </td>
                        <td
                          className={`p-3 text-center font-mono ${
                            row.price_change_pct > 0
                              ? "text-emerald-300"
                              : row.price_change_pct < 0
                                ? "text-rose-300"
                                : "text-zinc-300"
                          }`}
                          dir="ltr"
                        >
                          {formatPercent(row.price_change_pct)}
                        </td>
                        <td className="p-3 text-center font-mono text-zinc-200" dir="ltr">
                          {row.volume ? formatVolume(row.volume) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-zinc-800/50 bg-zinc-950/40 p-8 text-center text-sm text-zinc-400">
          {loading ? ar.flowDetectorLoading : ar.flowDetectorHidden}
        </div>
      )}
    </section>
  );
}

export default DailyLiquidityCard;
