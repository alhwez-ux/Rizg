"use client";

import { useState } from "react";

import { ar } from "@/lib/ar";
import { fetchRankingMatrix, type RankingRow } from "@/lib/rankingMatrix";

export function RankingRevealCard() {
  const [companies, setCompanies] = useState<RankingRow[]>([]);
  const [isRevealed, setIsRevealed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cached, setCached] = useState(false);

  const fetchRankedCompanies = async () => {
    if (isRevealed) {
      setIsRevealed(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const result = await fetchRankingMatrix();
      setCompanies(result.data);
      setCached(result.source === "cached");
      setIsRevealed(true);
    } catch {
      setCompanies([]);
      setError(ar.rankingLoadError);
      setIsRevealed(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 flex flex-col items-start justify-between gap-4 border-b border-zinc-800 pb-4 md:flex-row md:items-center">
        <div>
          <h2 className="text-xl font-bold text-zinc-50">{ar.rankingTitle}</h2>
          <p className="mt-1 text-xs text-zinc-500">{cached ? ar.rankingCached : ar.rankingHint}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            void fetchRankedCompanies();
          }}
          disabled={loading}
          className="flex shrink-0 items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-900/20 transition hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50"
        >
          {loading ? ar.rankingLoading : isRevealed ? ar.rankingHide : ar.rankingReveal}
        </button>
      </div>

      {isRevealed ? (
        <div className="animate-fadeIn overflow-x-auto transition-all">
          {error ? (
            <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {error}
            </p>
          ) : companies.length === 0 ? (
            <p className="text-sm text-zinc-500">{ar.rankingEmpty}</p>
          ) : (
            <table className="w-full border-collapse text-start">
              <thead>
                <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                  <th className="p-3 font-medium">{ar.tableColCompany}</th>
                  <th className="p-3 font-medium">{ar.rankingColCategory}</th>
                  <th className="p-3 font-medium">{ar.rankingColClose}</th>
                  <th className="p-3 font-medium">{ar.rankingColVolume}</th>
                  <th className="p-3 font-medium">{ar.rankingColGrowth}</th>
                  <th className="p-3 font-medium">{ar.rankingColDividend}</th>
                  <th className="p-3 font-medium">ROE</th>
                  <th className="p-3 font-medium">{ar.rankingColPe}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 text-sm">
                {companies.map((comp, index) => (
                  <tr key={comp.symbol} className="transition-colors hover:bg-zinc-950/40">
                    <td className="p-3">
                      <span className="inline-flex items-center gap-2 font-bold">
                        <span className="w-5 text-xs text-zinc-500" dir="ltr">
                          #{index + 1}
                        </span>
                        <span>{comp.name}</span>
                        <span className="font-mono text-xs font-normal text-zinc-400" dir="ltr">
                          ({comp.symbol})
                        </span>
                      </span>
                    </td>
                    <td className="p-3 text-xs font-semibold">
                      <span
                        className={`inline-block rounded-lg border px-2.5 py-1 ${
                          comp.matrix_score < 0
                            ? "border-rose-500/20 bg-rose-500/10 text-rose-400"
                            : "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                        }`}
                      >
                        {comp.category}
                      </span>
                    </td>
                    <td className="p-3 font-mono font-semibold text-zinc-100" dir="ltr">
                      {formatPrice(comp.last_price)}
                    </td>
                    <td className="p-3 font-mono text-zinc-200" dir="ltr">
                      {formatVolume(comp.volume)}
                    </td>
                    <td
                      className={`p-3 font-mono ${metricTone(comp.profit_growth)}`}
                      dir="ltr"
                    >
                      {formatPct(comp.profit_growth)}
                    </td>
                    <td className="p-3 font-mono text-zinc-200" dir="ltr">
                      {formatPct(comp.dividend_yield)}
                    </td>
                    <td className="p-3 font-mono text-zinc-200" dir="ltr">
                      {formatPct(comp.roe)}
                    </td>
                    <td className="p-3 font-mono text-zinc-200" dir="ltr">
                      {formatPe(comp.pe_ratio)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-zinc-800/50 bg-zinc-950/40 p-8 text-center text-sm text-zinc-400">
          {loading ? ar.rankingLoading : error ? error : ar.rankingHidden}
        </div>
      )}
    </section>
  );
}

export default RankingRevealCard;

function formatPct(value: number | null): string {
  if (value == null) return ar.missingMetric;
  return `${value}%`;
}

function formatPe(value: number | null): string {
  if (value == null) return ar.missingMetric;
  return `${value}x`;
}

function formatPrice(value: number | null): string {
  if (value == null) return ar.missingMetric;
  return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatVolume(value: number | null): string {
  if (value == null) return ar.missingMetric;
  return Math.round(value).toLocaleString("en-US");
}

function metricTone(value: number | null): string {
  if (value == null) return "text-zinc-500";
  return value >= 0 ? "text-emerald-400" : "text-rose-400";
}
