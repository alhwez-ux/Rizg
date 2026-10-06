"use client";

import { useEffect, useMemo, useState } from "react";

import { DataSkeleton } from "@/components/DataSkeleton";
import { ar } from "@/lib/ar";
import { displayCompanyTitle } from "@/lib/listedCompanies";
import { fetchRankingMatrix, type RankingRow } from "@/lib/rankingMatrix";
import { GradeBadge } from "@/components/GradeBadge";
import { compareByFinancialGrade, FINANCIAL_GRADES, financialGrade, type FinancialGrade } from "@/lib/rankingGrade";
import { passesShariahFilter, type ShariahFilter } from "@/lib/shariah";
import { useConnectionGuard } from "@/hooks/useConnectionGuard";

const GRADE_LABEL: Record<FinancialGrade, string> = {
  A: ar.rankingGradeA,
  B: ar.rankingGradeB,
  C: ar.rankingGradeC,
  D: ar.rankingGradeD,
  E: ar.rankingGradeE,
};

export function RankingRevealCard({ shariahFilter = "all" }: { shariahFilter?: ShariahFilter }) {
  const [companies, setCompanies] = useState<RankingRow[]>([]);
  const [isRevealed, setIsRevealed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cached, setCached] = useState(false);
  const [gradeFilter, setGradeFilter] = useState<FinancialGrade | "all">("all");
  const { isConnected } = useConnectionGuard();
  const visible = useMemo(
    () =>
      companies
        .filter((comp) => passesShariahFilter(comp.symbol, shariahFilter))
        .slice()
        .sort(compareByFinancialGrade),
    [companies, shariahFilter],
  );
  const graded = useMemo(() => {
    const buckets: Record<FinancialGrade, RankingRow[]> = { A: [], B: [], C: [], D: [], E: [] };
    for (const row of visible) {
      const grade = financialGrade(row);
      if (!grade) continue;
      buckets[grade].push(row);
    }
    for (const grade of FINANCIAL_GRADES) {
      buckets[grade].sort((left, right) => right.matrix_score - left.matrix_score || left.symbol.localeCompare(right.symbol));
    }
    return buckets;
  }, [visible]);
  const shown = gradeFilter === "all" ? visible : graded[gradeFilter];

  const fetchRankedCompanies = async () => {
    if (!isConnected) return;
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
      setGradeFilter("all");
      setIsRevealed(true);
    } catch {
      setCompanies([]);
      setError(ar.rankingLoadError);
      setIsRevealed(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isConnected || !isRevealed) return;
    const timer = window.setInterval(() => {
      void fetchRankingMatrix()
        .then((result) => {
          setCompanies(result.data);
          setCached(result.source === "cached");
          setError(null);
        })
        .catch(() => {
          /* keep the last successful snapshot while TickChart refreshes */
        });
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [isConnected, isRevealed]);

  return (
    <section className="rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 flex flex-col items-center justify-center gap-4 border-b border-zinc-800 pb-4 text-center">
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
          ) : visible.length === 0 ? (
            <p className="text-sm text-zinc-500">{shariahFilter === "pure" ? ar.shariahFilterEmpty : ar.rankingEmpty}</p>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-center gap-2">
                <button
                  type="button"
                  onClick={() => setGradeFilter("all")}
                  className={`rounded-full border px-3 py-1 text-xs font-bold ${gradeFilter === "all" ? "border-zinc-500 bg-zinc-800 text-zinc-100" : "border-zinc-800 text-zinc-400"}`}
                >
                  {ar.tableFilterAll}
                </button>
                {FINANCIAL_GRADES.map((grade) => {
                  const count = graded[grade].length;
                  const selected = grade === gradeFilter;
                  return (
                    <button
                      key={grade}
                      type="button"
                      disabled={count === 0}
                      onClick={() => setGradeFilter(grade)}
                      className={`rounded-full border px-3 py-1 text-xs font-bold disabled:opacity-30 ${gradeTone(grade, selected)}`}
                    >
                      {GRADE_LABEL[grade]}
                      <span className="ms-1 font-mono opacity-70" dir="ltr">
                        {count}
                      </span>
                    </button>
                  );
                })}
              </div>
              <RankingTable rows={shown} />
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-zinc-800/50 bg-zinc-950/40 p-8 text-center text-sm text-zinc-400">
          {loading ? <DataSkeleton kind="table" rows={6} /> : error ? error : ar.rankingHidden}
        </div>
      )}
    </section>
  );
}

export default RankingRevealCard;

function RankingTable({ rows }: { rows: RankingRow[] }) {
  return (
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
        {rows.map((comp, index) => {
          const name = displayCompanyTitle(comp.symbol, comp.name);
          const letter = financialGrade(comp);
          return (
            <tr key={comp.symbol} className="transition-colors hover:bg-zinc-950/40">
              <td className="p-3">
                <span className="flex flex-col gap-0.5">
                  <span className="inline-flex items-center gap-2 font-bold text-zinc-50">
                    <span className="w-5 text-xs text-zinc-500" dir="ltr">
                      #{index + 1}
                    </span>
                    <span>{name || ar.dossierMissing}</span>
                  </span>
                  <span className="ps-7 font-mono text-xs font-normal text-zinc-400" dir="ltr">
                    {comp.symbol}
                  </span>
                </span>
              </td>
              <td className="p-3 text-xs font-semibold">
                {letter ? <GradeBadge grade={letter} /> : <span className="text-zinc-500">{ar.dossierMissing}</span>}
              </td>
              <td className="p-3 font-mono font-semibold text-zinc-100" dir="ltr">
                {formatPrice(comp.last_price)}
              </td>
              <td className="p-3 font-mono text-zinc-200" dir="ltr">
                {formatVolume(comp.volume)}
              </td>
              <td className={`p-3 font-mono ${metricTone(comp.profit_growth)}`} dir="ltr">
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
          );
        })}
      </tbody>
    </table>
  );
}

function gradeTone(grade: FinancialGrade, selected: boolean): string {
  const strong = selected ? "ring-1 ring-white/30" : "";
  if (grade === "A") return `border-emerald-400/50 bg-emerald-600 text-white ${strong}`;
  if (grade === "B") return `border-teal-400/40 bg-teal-700 text-white ${strong}`;
  if (grade === "C") return `border-amber-400/40 bg-amber-700 text-white ${strong}`;
  if (grade === "D") return `border-orange-400/40 bg-orange-800 text-white ${strong}`;
  return `border-rose-400/50 bg-rose-700 text-white ${strong}`;
}

function formatPct(value: number | null): string {
  if (value == null) return ar.missingMetric;
  return `${value}%`;
}

function formatPe(value: number | null): string {
  if (value == null) return ar.missingMetric;
  return `${value}x`;
}

function formatPrice(value: number | null): string {
  if (value == null || !Number.isFinite(value) || value <= 0) return ar.missingMetric;
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
