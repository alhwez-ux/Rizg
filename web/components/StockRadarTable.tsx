"use client";

import { useMemo, useState } from "react";

import { RecommendationStatus } from "@/components/SignalBadge";
import { useRadarRecommendations } from "@/hooks/useRadarRecommendations";
import { ar } from "@/lib/ar";
import { formatCompact, formatMoney, formatPrice, type RecommendationFlag } from "@/lib/liquidity";
import { type RadarTableRow } from "@/lib/firebase";
import { type ScreenerRow } from "@/lib/screener";

type StatusFilter = "ALL" | "PURE" | "MIXED";

const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";

export function StockRadarTable({
  rows,
  loading = false,
  usingSample = false,
  error = null,
  onRetry,
  selectedSymbol,
  onSelect,
  screenerRows = [],
}: {
  rows: RadarTableRow[];
  loading?: boolean;
  usingSample?: boolean;
  error?: string | null;
  onRetry?: () => void;
  selectedSymbol?: string;
  onSelect?: (symbol: string) => void;
  screenerRows?: ScreenerRow[];
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");

  const liquidityBySymbol = useMemo(() => {
    const map = new Map<string, ScreenerRow>();
    for (const row of screenerRows) map.set(row.symbol, row);
    return map;
  }, [screenerRows]);
  const recommendations = useRadarRecommendations(screenerRows);

  const filtered = useMemo(() => {
    const needle = normalizeSearch(query);
    return rows
      .filter((row) => (statusFilter === "ALL" ? true : row.currentStatus === statusFilter))
      .filter((row) => {
        if (!needle) return true;
        const haystack = normalizeSearch(
          `${row.symbol} ${row.companyNameAr} ${row.companyNameEn} ${row.sector}`,
        );
        return haystack.includes(needle);
      })
      .sort((a, b) => {
        const rateA = a.purificationRate ?? 0;
        const rateB = b.purificationRate ?? 0;
        if (rateA !== rateB) return rateB - rateA;
        return a.symbol.localeCompare(b.symbol, "en");
      });
  }, [query, rows, statusFilter]);

  const pureCount = rows.filter((row) => row.currentStatus === "PURE").length;
  const mixedCount = rows.filter((row) => row.currentStatus === "MIXED").length;

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-center justify-between gap-3 rounded-2xl border border-zinc-800/80 bg-tape-panel/90 px-4 py-4 text-start shadow-glow transition hover:border-emerald-500/40 hover:bg-zinc-900/60 sm:px-5"
      >
        <span className="flex min-w-0 flex-col gap-1">
          <span className="text-lg font-semibold text-zinc-100">{ar.tableShowList}</span>
          <span className="text-xs text-zinc-500">{ar.radarHintCompliant}</span>
        </span>
        <span className="shrink-0 rounded-full border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300">
          <span className="font-mono text-zinc-100" dir="ltr">
            {rows.length}
          </span>{" "}
          {ar.tableCount}
        </span>
      </button>
    );
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-zinc-800/80 bg-tape-panel/90 shadow-glow">
      <header className="flex flex-col gap-4 border-b border-zinc-800/80 px-4 py-4 sm:px-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-zinc-100">{ar.radarTitle}</h2>
            <p className="mt-1 text-xs text-zinc-500">{ar.radarHintCompliant}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs text-zinc-500">
              <span className="font-mono text-zinc-300" dir="ltr">
                {filtered.length}
              </span>{" "}
              {ar.tableCount}
            </p>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-full border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 transition hover:border-emerald-500 hover:text-emerald-300"
            >
              {ar.tableHideList}
            </button>
          </div>
        </div>

        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <label className="relative block min-w-0 flex-1">
            <span className="sr-only">{ar.tableSearch}</span>
            <svg
              aria-hidden
              viewBox="0 0 20 20"
              className="pointer-events-none absolute inset-y-0 start-3 my-auto h-4 w-4 text-zinc-500"
              fill="none"
            >
              <path
                d="M8.5 14.5a6 6 0 1 0 0-12 6 6 0 0 0 0 12Zm8 2.5-3.7-3.7"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={ar.tableSearch}
              className="w-full rounded-xl border border-zinc-800 bg-zinc-950 py-2.5 pe-3 ps-10 text-sm text-zinc-100 outline-none ring-emerald-500/40 placeholder:text-zinc-600 focus:ring"
            />
          </label>

          <div className="flex rounded-xl border border-zinc-800 bg-zinc-950 p-1 text-xs font-medium">
            <FilterChip
              active={statusFilter === "ALL"}
              onClick={() => setStatusFilter("ALL")}
              label={`${ar.tableFilterAll} (${rows.length})`}
            />
            <FilterChip
              active={statusFilter === "PURE"}
              onClick={() => setStatusFilter("PURE")}
              label={`${ar.tableFilterPure} (${pureCount})`}
              tone="pure"
            />
            <FilterChip
              active={statusFilter === "MIXED"}
              onClick={() => setStatusFilter("MIXED")}
              label={`${ar.tableFilterMixed} (${mixedCount})`}
              tone="mixed"
            />
          </div>
        </div>

        {error ? (
          <div className="flex flex-col gap-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200 sm:flex-row sm:items-center sm:justify-between">
            <p>{error}</p>
            {onRetry ? (
              <button
                type="button"
                onClick={() => onRetry()}
                disabled={loading}
                className="shrink-0 rounded-lg border border-rose-400/30 bg-rose-500/20 px-3 py-1.5 font-medium text-rose-100 hover:bg-rose-500/30 disabled:opacity-50"
              >
                {ar.radarRetry}
              </button>
            ) : null}
          </div>
        ) : usingSample ? (
          <p className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            {ar.tableSample}
          </p>
        ) : null}
      </header>

      <div className="overflow-x-auto">
        <table className="min-w-[980px] w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-start text-[11px] uppercase tracking-wide text-zinc-500">
              <th className="px-4 py-3 font-medium sm:px-5">{ar.tableColCompany}</th>
              <th className="px-3 py-3 font-medium">{ar.tableColRecommendation}</th>
              <th className="px-3 py-3 font-medium">{ar.tableColStatus}</th>
              <th className="px-3 py-3 font-medium">{ar.tableColSector}</th>
              <th className="px-3 py-3 font-medium">{ar.tableColPurification}</th>
              <th className="px-3 py-3 font-medium">{ar.tableColDebt}</th>
              <th className="px-3 py-3 font-medium">{ar.tableColImpure}</th>
              <th className="px-3 py-3 font-medium">{ar.tableColFlow}</th>
              <th className="px-4 py-3 font-medium sm:px-5">{ar.tableColQuarter}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <SkeletonRows />
            ) : error ? (
              <tr>
                <td colSpan={9} className="h-24" />
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-14 text-center text-sm text-zinc-500">
                  {ar.tableEmpty}
                </td>
              </tr>
            ) : (
              filtered.map((row) => {
                const tape = liquidityBySymbol.get(row.symbol);
                const selected = row.symbol === selectedSymbol;
                return (
                  <tr
                    key={row.symbol}
                    onClick={() => onSelect?.(row.symbol)}
                    className={`cursor-pointer border-b border-zinc-800/70 transition hover:bg-zinc-900/60 ${
                      selected ? "bg-emerald-500/5" : ""
                    }`}
                  >
                    <td className="px-4 py-3.5 sm:px-5">
                      <p className="font-mono text-base font-semibold text-zinc-50" dir="ltr">
                        {row.symbol}
                      </p>
                      <p className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-xs text-zinc-300">{row.companyNameAr}</span>
                        <RecommendationStatus value={recommendations.get(row.symbol) ?? null} />
                      </p>
                      <p className="truncate text-[11px] text-zinc-500">{row.companyNameEn}</p>
                    </td>
                    <td className="px-3 py-3.5">
                      <RecommendationCell value={recommendations.get(row.symbol) ?? null} />
                    </td>
                    <td className="px-3 py-3.5">
                      <StatusBadge status={row.currentStatus} />
                    </td>
                    <td className="px-3 py-3.5 text-zinc-300">{row.sector}</td>
                    <td className="px-3 py-3.5">
                      <PurificationMeter rate={row.purificationRate} status={row.currentStatus} />
                    </td>
                    <td className="px-3 py-3.5">
                      <RatioCell value={row.debtRatio} />
                    </td>
                    <td className="px-3 py-3.5">
                      <RatioCell value={row.impureIncomeRatio} />
                    </td>
                    <td className="px-3 py-3.5">
                      {tape ? (
                        <div>
                          <p
                            dir="ltr"
                            className={`font-mono text-xs ${
                              tape.net_flow > 0
                                ? "text-emerald-400"
                                : tape.net_flow < 0
                                  ? "text-rose-400"
                                  : "text-zinc-400"
                            }`}
                          >
                            {formatMoney(tape.net_flow)}
                          </p>
                          <p dir="ltr" className="font-mono text-[11px] text-zinc-500">
                            {formatPrice(tape.price || null)}
                          </p>
                        </div>
                      ) : (
                        <span className="text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5 font-mono text-xs text-zinc-400 sm:px-5" dir="ltr">
                      {row.quarter ?? "—"}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FilterChip({
  active,
  onClick,
  label,
  tone,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  tone?: "pure" | "mixed";
}) {
  const activeClass = active
    ? tone === "pure"
      ? "bg-emerald-500/20 text-emerald-300"
      : tone === "mixed"
        ? "bg-amber-500/20 text-amber-200"
        : "bg-zinc-700 text-zinc-100"
    : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300";

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-lg px-3 py-1.5 transition ${activeClass}`}
    >
      {label}
    </button>
  );
}

function RecommendationCell({ value }: { value: RecommendationFlag | null | undefined }) {
  if (value === "دخول") {
    return (
      <span
        className="inline-block text-[15px] font-semibold tracking-tight [text-rendering:geometricPrecision]"
        style={{
          color: "#00E676",
          textShadow: "0 0 8px rgba(0, 230, 118, 0.55), 0 0 18px rgba(0, 230, 118, 0.22)",
        }}
      >
        دخول
      </span>
    );
  }
  if (value === "خروج") {
    return (
      <span
        className="inline-block text-[15px] font-semibold tracking-tight [text-rendering:geometricPrecision]"
        style={{
          color: "#F87171",
          textShadow: "0 0 6px rgba(248, 113, 113, 0.28)",
        }}
      >
        خروج
      </span>
    );
  }
  return (
    <span className="inline-block text-[13px] font-medium tracking-tight text-zinc-500 [text-rendering:geometricPrecision]">
      —
    </span>
  );
}

function StatusBadge({ status }: { status: "PURE" | "MIXED" }) {
  if (status === "PURE") {
    return (
      <span className="inline-flex rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-300">
        {ar.tablePure}
      </span>
    );
  }
  return (
    <span className="inline-flex rounded-full border border-amber-400/30 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold text-amber-200">
      {ar.tableMixed}
    </span>
  );
}

function PurificationMeter({
  rate,
  status,
}: {
  rate: number | null;
  status: "PURE" | "MIXED";
}) {
  const value = rate ?? 0;
  if (status === "PURE" && value <= 0) {
    return (
      <div className="min-w-[140px]">
        <div className="h-1.5 overflow-hidden rounded-full bg-emerald-500/15">
          <span className="block h-full w-[8%] rounded-full bg-emerald-400" />
        </div>
        <p className="mt-1.5 text-xs font-medium text-emerald-400">{ar.tableNoPurification}</p>
      </div>
    );
  }

  const bar = Math.min(100, (value / 0.05) * 100);
  const tone = value < 0.01 ? "bg-amber-400" : "bg-rose-400";
  const text = value < 0.01 ? "text-amber-200" : "text-rose-300";

  return (
    <div className="min-w-[140px]">
      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <span className={`block h-full rounded-full ${tone}`} style={{ width: `${Math.max(bar, 4)}%` }} />
      </div>
      <p dir="ltr" className={`mt-1.5 font-mono text-xs font-semibold ${text}`}>
        {formatRate(value, 2)}
      </p>
    </div>
  );
}

function RatioCell({ value }: { value: number | null }) {
  if (value == null) return <span className="text-zinc-600">—</span>;
  return (
    <span dir="ltr" className="font-mono text-xs text-zinc-200">
      {formatRate(value, 1)}
    </span>
  );
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 4 }, (_, index) => (
        <tr key={index} className="border-b border-zinc-800/70">
          {Array.from({ length: 9 }, (__, cell) => (
            <td key={cell} className="px-4 py-4">
              <span className="block h-3 w-20 animate-pulse rounded bg-zinc-800" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

function normalizeSearch(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[٠-٩]/g, (digit) => String(ARABIC_DIGITS.indexOf(digit)));
}

function formatRate(value: number | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  const pct = Math.abs(value) <= 1 ? value * 100 : value;
  return `${formatCompact(Math.abs(pct), digits)}%`;
}
