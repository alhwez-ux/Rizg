"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { LiquidityRadarCard } from "@/components/LiquidityRadarCard";
import { CloseRecommendationIcon } from "@/components/CloseRecommendationIcon";
import { useTasiSession } from "@/hooks/useTasiSession";
import { ar } from "@/lib/ar";
import { formatPrice } from "@/lib/liquidity";
import {
  fetchMarketRecommendations,
  type MarketRecommendation,
  type RecommendationKind,
  type RecommendationScanMode,
} from "@/lib/recommendations";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";

type FilterKind = "all" | RecommendationKind;
type SortKey = "confidence" | "close" | "symbol";

const LIVE_POLL_MS = 12_000;
const CLOSE_POLL_MS = 45_000;
const MAX_ATTEMPTS = 3;

function isTimeoutError(error: unknown): boolean {
  return error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
}

export function RecommendationsCard() {
  const [rows, setRows] = useState<MarketRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cached, setCached] = useState(false);
  const [sessionLabel, setSessionLabel] = useState<string | null>(null);
  const [scanMode, setScanMode] = useState<RecommendationScanMode | string>("end_of_day");
  const { live: sessionLive, label: sessionPhaseLabel } = useTasiSession();
  const [filter, setFilter] = useState<FilterKind>("all");
  const [sortKey, setSortKey] = useState<SortKey>("confidence");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [selected, setSelected] = useState<MarketRecommendation | null>(null);
  const inflight = useRef(false);
  const rowsRef = useRef<MarketRecommendation[]>([]);

  const load = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    setLoading(true);
    setError(null);
    let lastError: unknown = null;
    try {
      for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
        try {
          const result = await fetchMarketRecommendations();
          const data = result.data;
          rowsRef.current = data;
          setRows(data);
          setCached(result.source === "cached");
          setSessionLabel(result.session_label || null);
          setScanMode(result.scan_mode === "live" ? "live" : "end_of_day");
          setLoaded(true);
          setError(null);
          setSelected((current) => {
            if (!current) return null;
            return data.find((row) => row.symbol === current.symbol) ?? null;
          });
          lastError = null;
          break;
        } catch (err) {
          lastError = err;
          if (!isTimeoutError(err) || attempt === MAX_ATTEMPTS - 1) {
            break;
          }
        }
      }
      if (lastError) {
        setLoaded(true);
        if (rowsRef.current.length === 0) {
          setError(ar.recoLoadError);
        }
      }
    } finally {
      inflight.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const onRefresh = () => {
      void load();
    };
    window.addEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    return () => {
      window.removeEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    };
  }, [load]);

  useEffect(() => {
    const interval = scanMode === "live" || sessionLive ? LIVE_POLL_MS : CLOSE_POLL_MS;
    const timer = window.setInterval(() => {
      void load();
    }, interval);
    return () => window.clearInterval(timer);
  }, [load, scanMode, sessionLive]);

  const visible = useMemo(() => {
    const filtered = filter === "all" ? rows : rows.filter((row) => row.signal_kind === filter);
    const copy = [...filtered];
    copy.sort((left, right) => {
      const direction = sortDir === "asc" ? 1 : -1;
      if (sortKey === "symbol") {
        return left.symbol.localeCompare(right.symbol) * direction;
      }
      if (sortKey === "close") {
        return (left.close_price - right.close_price) * direction;
      }
      return (left.confidence_score - right.confidence_score) * direction;
    });
    return copy;
  }, [filter, rows, sortDir, sortKey]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((current) => (current === "desc" ? "asc" : "desc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "symbol" ? "asc" : "desc");
  };

  const live = scanMode === "live" || sessionLive;
  const buttonName = live ? ar.recoButtonLive : ar.recoButtonEod;
  const title = buttonName;
  const hint = cached && !live ? ar.recoCached : live ? ar.recoHintLive : ar.recoHintEod;
  const badge = live ? ar.recoLive : sessionLabel || sessionPhaseLabel || ar.recoClosed;
  const emptyLabel = live ? ar.recoEmptyLive : ar.recoEmptyEod;
  const loadingLabel = live ? ar.recoLoadingLive : ar.recoLoadingEod;
  const priceLabel = live ? ar.recoColPriceLive : ar.recoColCloseEod;
  const horizonLabel = live ? ar.recoHorizonLive : ar.recoHorizon;

  return (
    <section className="rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 flex flex-col items-center justify-center gap-4 border-b border-zinc-800 pb-4 text-center">
        <div>
          <h2 className={`flex items-center justify-center gap-2 text-xl font-bold ${live ? "text-sky-100" : "text-emerald-100"}`}>
            <span
              className={`inline-flex h-9 w-9 items-center justify-center rounded-xl ${
                live ? "bg-sky-500/20 text-sky-300" : "bg-emerald-100 text-emerald-800"
              }`}
            >
              {live ? <span aria-hidden="true">⚡</span> : <CloseRecommendationIcon className="h-5 w-5" />}
            </span>
            {title}
          </h2>
          <p className="mt-1 text-xs text-zinc-500">{hint}</p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <span
            className={`rounded-xl border px-3 py-1 text-xs font-semibold ${
              live
                ? "border-sky-500/30 bg-sky-500/10 text-sky-200"
                : "border-emerald-500/20 bg-emerald-100 text-emerald-900"
            }`}
          >
            {badge}
          </span>
          <button
            type="button"
            onClick={() => {
              void load();
            }}
            disabled={loading}
            aria-busy={loading}
            aria-label={buttonName}
            className={`inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-lg transition disabled:opacity-50 ${
              live
                ? "bg-gradient-to-r from-sky-500 to-cyan-500 shadow-sky-900/30 hover:from-sky-400 hover:to-cyan-400"
                : "bg-gradient-to-r from-sky-600 to-teal-600 shadow-sky-900/20 hover:from-sky-500 hover:to-teal-500"
            }`}
          >
            {loading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" /> : null}
            {loading ? ar.recoRefreshing : buttonName}
          </button>
        </div>
      </div>

      {loaded ? (
        <div className="mb-4 flex flex-wrap justify-center gap-2">
          {(
            [
              ["all", ar.recoFilterAll],
              ["bounce", ar.recoFilterBounce],
              ["momentum", ar.recoFilterMomentum],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                filter === id
                  ? "border-sky-500/40 bg-sky-500/15 text-sky-300"
                  : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}

      {loading && visible.length === 0 ? (
        <RecoSpinner label={loadingLabel} />
      ) : error && visible.length === 0 ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : !loaded ? (
        <RecoSpinner label={loadingLabel} />
      ) : visible.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">{emptyLabel}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-start">
            <thead>
              <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                <SortHeader label={ar.recoColSymbol} active={sortKey === "symbol"} onClick={() => toggleSort("symbol")} />
                <th className="p-3 font-medium">{ar.tableColCompany}</th>
                <th className="p-3 font-medium">{ar.recoColSignal}</th>
                <SortHeader label={priceLabel} active={sortKey === "close"} onClick={() => toggleSort("close")} />
                <th className="p-3 font-medium">{ar.recoColEntry}</th>
                <th className="p-3 font-medium">{ar.target}</th>
                <th className="p-3 font-medium">{ar.stopLoss}</th>
                <SortHeader
                  label={ar.recoColConfidence}
                  active={sortKey === "confidence"}
                  onClick={() => toggleSort("confidence")}
                />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 text-sm">
              {visible.map((row) => {
                const active = selected?.symbol === row.symbol;
                return (
                  <tr
                    key={row.symbol}
                    className={`cursor-pointer transition-colors hover:bg-zinc-950/50 ${active ? "bg-sky-950/30" : ""}`}
                    tabIndex={0}
                    onClick={() => setSelected(row)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelected(row);
                      }
                    }}
                  >
                    <td className="p-3 font-mono text-sky-400" dir="ltr">
                      {row.symbol}
                    </td>
                    <td className="p-3 font-semibold text-zinc-100">{row.name}</td>
                    <td className="p-3">
                      <span
                        className={`rounded-xl border px-2 py-1 text-[11px] font-semibold ${
                          row.signal_kind === "bounce"
                            ? "border-amber-500/20 bg-amber-500/10 text-amber-300"
                            : "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                        }`}
                      >
                        {row.signal_type}
                      </span>
                      {row.entry ? (
                        <span className="ms-2 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                          {ar.recoEntryMet}
                        </span>
                      ) : null}
                      <span className="ms-2 rounded-full border border-zinc-700 px-2 py-0.5 text-[10px] text-zinc-400">
                        {horizonLabel}
                      </span>
                    </td>
                    <td className="p-3 font-bold" dir="ltr">
                      {formatPrice(row.close_price)}
                    </td>
                    <td className="p-3 text-zinc-200" dir="ltr">
                      {row.entry_price}
                    </td>
                    <td className="p-3 font-semibold text-emerald-400" dir="ltr">
                      {row.target_price}
                    </td>
                    <td className="p-3 font-semibold text-rose-400" dir="ltr">
                      {row.stop_loss}
                    </td>
                    <td className="p-3 font-bold text-sky-300">{row.confidence}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected ? (
        <div className="mt-5 space-y-4 border-t border-zinc-800 pt-5">
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 text-xs text-zinc-400">
            <strong className="mb-1 block text-zinc-200">{ar.recoReason}</strong>
            {selected.reason}
          </div>
          <LiquidityRadarCard symbol={selected.symbol} symbolName={selected.name} />
        </div>
      ) : null}
    </section>
  );
}

function RecoSpinner({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10" role="status" aria-live="polite">
      <span className="h-10 w-10 animate-spin rounded-full border-2 border-zinc-700 border-t-sky-400" />
      <p className="max-w-md text-center text-sm text-zinc-400">{label}</p>
    </div>
  );
}

function SortHeader({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <th className="p-3 font-medium">
      <button type="button" onClick={onClick} className={`hover:text-zinc-200 ${active ? "text-sky-400" : ""}`}>
        {label}
      </button>
    </th>
  );
}

export default RecommendationsCard;
